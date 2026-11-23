import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from real_scraper import evaluate_for_peter, scrape_all_real_sources

FEED_PATH = os.path.join("data", "live_feed.json")
GMAIL_QUEUE_PATH = os.path.join("data", "gmail_queue.json")


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_key(company, title):
    c = re.sub(r"[^a-z0-9\u0600-\u06FF]+", "", str(company or "").lower())
    t = re.sub(r"[^a-z0-9\u0600-\u06FF]+", "", str(title or "").lower())
    return f"{c[:24]}::{t[:36]}"


def send_ntfy_alert(job, ntfy_topic, pwa_base_url):
    if not ntfy_topic:
        return
    url = f"https://ntfy.sh/{urllib.parse.quote(ntfy_topic)}"
    title = f"{job['company']} — {job['title']} ({job['fit']['score']}%)"
    body = f"{job['fit']['summary']}\nالمشوار: {job['commute']['summary']}"
    headers = {
        "Title": title[:120].encode("utf-8"),
        "Priority": "high",
        "Tags": "briefcase,dart",
    }
    if pwa_base_url:
        headers["Click"] = pwa_base_url.strip()
    try:
        req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def ingest_gmail_queue(now_iso):
    queue_data = load_json(GMAIL_QUEUE_PATH, {"items": []})
    raw_items = queue_data.get("items", []) if isinstance(queue_data, dict) else []
    converted = []
    for idx, item in enumerate(raw_items):
        title = item.get("title") or "فرصة من تنبيهات Gmail"
        company = item.get("company") or "Gmail Job Alert"
        loc = item.get("location") or "Cairo, Egypt"
        tasks = item.get("tasks") or ""
        ev = evaluate_for_peter(title, company, loc, tasks)
        if not ev:
            continue
        jid = f"gm-{abs(hash(item.get('url') or title))}-{idx}"
        converted.append({
            "id": jid,
            "company": company,
            "title": title,
            "work_mode": "Gmail Job Alert",
            "location": loc,
            "primary_url": item.get("url") or "https://mail.google.com",
            "sources": [item.get("source_name") or "Gmail Alert"],
            "discovered_at": now_iso,
            "fit": {
                "score": ev["fit_score"],
                "summary": ev["summary"],
                "recommended_project": "مشروع DEPI لتحليل البيانات + Power BI.",
                "evidence_pairs": ev["evidence_pairs"],
            },
            "commute": {
                "score": ev["commute_score"],
                "summary": ev["commute_summary"],
            },
            "receipt": {
                "apply_state": "OPEN",
                "apply_state_ar": "مفتوح ومتحقق ✓",
                "egypt_eligibility": f"مؤكد: {loc}",
                "first_published": (item.get("posted_at") or now_iso)[:10],
                "last_verified": now_iso,
            },
        })
    if raw_items:
        save_json(GMAIL_QUEUE_PATH, {"items": []})
    return converted


def main():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing_feed = load_json(FEED_PATH, {"meta": {}, "jobs": {}})
    existing_jobs = existing_feed.get("jobs", {}) if isinstance(existing_feed, dict) else {}

    scraped_list, source_stats = scrape_all_real_sources()
    gmail_list = ingest_gmail_queue(now_iso)
    source_stats["gmail_alerts"] = len(gmail_list)

    combined = scraped_list + gmail_list

    # Index existing jobs by normalized (company, title) for deduplication
    by_norm = {}
    for jid, jdata in existing_jobs.items():
        nk = normalize_key(jdata.get("company"), jdata.get("title"))
        by_norm[nk] = jid

    new_high_fit = []
    for item in combined:
        nk = normalize_key(item.get("company"), item.get("title"))
        if nk in by_norm:
            old_id = by_norm[nk]
            old_job = existing_jobs[old_id]
            merged_sources = list(dict.fromkeys((old_job.get("sources") or []) + (item.get("sources") or [])))
            old_job["sources"] = merged_sources
            old_job["receipt"]["last_verified"] = now_iso
            if item["fit"]["score"] > old_job.get("fit", {}).get("score", 0):
                old_job["fit"] = item["fit"]
        else:
            jid = item["id"]
            existing_jobs[jid] = item
            by_norm[nk] = jid
            if item["fit"]["score"] >= 78:
                new_high_fit.append(item)

    # Keep newest / highest scoring 120 jobs so feed stays fast on mobile
    sorted_pairs = sorted(
        existing_jobs.items(),
        key=lambda kv: (kv[1].get("discovered_at", ""), kv[1].get("fit", {}).get("score", 0)),
        reverse=True,
    )[:120]
    trimmed_jobs = dict(sorted_pairs)

    out_feed = {
        "meta": {
            "last_successful_run": now_iso,
            "total_active": len(trimmed_jobs),
            "source_stats": source_stats,
        },
        "jobs": trimmed_jobs,
    }
    save_json(FEED_PATH, out_feed)

    ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
    pwa_base_url = os.environ.get("PWA_BASE_URL", "").strip()
    for top_job in new_high_fit[:3]:
        send_ntfy_alert(top_job, ntfy_topic, pwa_base_url)

    print(f"Scan complete: {len(combined)} fetched, {len(trimmed_jobs)} total in live_feed.json, {len(new_high_fit)} new alerts.")


if __name__ == "__main__":
    main()
