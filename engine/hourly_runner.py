import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from matcher import (
        PRIORITY_THRESHOLD,
        compute_job_identity,
        evaluate_evidence_fit,
        evaluate_weekly_commute,
        run_self_tests,
        verify_receipt_and_status,
    )
    run_self_tests()
except Exception as exc:
    print(f"[CRITICAL HALT] matcher.py verification failed: {exc}", file=sys.stderr)
    sys.exit(1)

from real_scraper import scrape_all_real_sources

FEED_PATH = os.path.join("data", "live_feed.json")
PRIVATE_GMAIL_QUEUE = os.path.join("data", "gmail_queue.json")
MAX_AGE_HOURS = 24


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


def is_within_last_24h(date_str, now_dt):
    if not date_str:
        return True
    s = str(date_str).strip()
    try:
        if len(s) == 10 and re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            dt = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return (now_dt - dt) <= timedelta(hours=MAX_AGE_HOURS)
    except Exception:
        return True


def send_ntfy_alert(job, ntfy_topic, pwa_base_url):
    if not ntfy_topic:
        return "UNCONFIGURED"
    url = f"https://ntfy.sh/{urllib.parse.quote(ntfy_topic)}"
    fit_score = job.get("fit", {}).get("score")
    score_txt = f" ({fit_score}%)" if fit_score is not None else ""
    title = f"{job['company']} — {job['title']}{score_txt}"
    body = f"{job['fit']['reason_first']}\n{job['commute']['summary']}"

    headers = {
        "Title": title[:120].encode("utf-8"),
        "Priority": "high",
        "Tags": "briefcase",
    }
    if pwa_base_url:
        base = pwa_base_url.strip().rstrip("/")
        headers["Click"] = f"{base}/?job={urllib.parse.quote(job['id'])}"

    try:
        req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if 200 <= resp.status < 300:
                return "ACCEPTED"
            return f"FAILED_HTTP_{resp.status}"
    except Exception:
        return "FAILED_NETWORK"


def build_evaluated_card(raw_item, now_iso):
    company = raw_item.get("company") or "جهة معلنة"
    title = raw_item.get("title") or "فرصة عمل"
    location = raw_item.get("location")
    work_mode = raw_item.get("work_mode")
    source_name = raw_item.get("source_name") or "مصدر عام"
    source_category = raw_item.get("source_category") or "job_board"
    job_url = raw_item.get("url") or ""

    exact_id, family_id = compute_job_identity(
        company=company,
        title=title,
        req_id=raw_item.get("req_id"),
        location=location,
        canonical_url=job_url,
    )

    receipt = verify_receipt_and_status(
        {
            "url": job_url,
            "location": location,
            "work_mode": work_mode,
            "eligible_regions": raw_item.get("eligible_regions"),
            "first_published": raw_item.get("first_published"),
            "discovered_at": raw_item.get("discovered_at") or now_iso,
            "description": raw_item.get("tasks") or "",
            "http_status": raw_item.get("http_status", 200),
            "has_apply_button": raw_item.get("has_apply_button", False),
        },
        now_iso,
    )

    fit = evaluate_evidence_fit(
        {
            "title": title,
            "location": location,
            "required_text": raw_item.get("required_text") or title,
            "tasks": raw_item.get("tasks") or "",
            "bonus_text": raw_item.get("bonus_text") or "",
        }
    )

    commute = evaluate_weekly_commute(
        location_raw=location,
        work_mode_raw=work_mode,
        onsite_days_per_week=raw_item.get("onsite_days_per_week"),
        egypt_status=receipt["egypt_status"],
    )

    is_training = bool(
        re.search(
            r"\b(intern|internship|trainee|graduate program|تدريب|متدرب)\b",
            f"{title} {raw_item.get('tasks', '')}",
            re.I,
        )
    )

    return {
        "id": exact_id,
        "family_id": family_id,
        "probable_duplicate_of": None,
        "company": company,
        "title": title,
        "sources": [source_name],
        "source_category": source_category,
        "all_urls": [job_url] if job_url else [],
        "primary_url": job_url,
        "location": location,
        "work_mode": work_mode,
        "is_training": is_training,
        "receipt": receipt,
        "fit": fit,
        "commute": commute,
        "discovered_at": raw_item.get("discovered_at") or now_iso,
    }


def read_local_gmail_queue_if_present(now_iso):
    if not os.path.exists(PRIVATE_GMAIL_QUEUE):
        return [], 0
    q_data = load_json(PRIVATE_GMAIL_QUEUE, {"items": []})
    items = q_data.get("items", []) if isinstance(q_data, dict) else []
    cards = []
    for it in items:
        cards.append(
            build_evaluated_card(
                {
                    "company": it.get("company") or "تنبيه بريد",
                    "title": it.get("title") or "فرصة من تنبيهات البريد",
                    "location": it.get("location"),
                    "work_mode": it.get("work_mode"),
                    "source_name": it.get("source_name") or "WUZZUF / Email Alert",
                    "source_category": "email_alert",
                    "url": it.get("url") or "",
                    "first_published": it.get("posted_at"),
                    "discovered_at": now_iso,
                    "required_text": f"{it.get('title', '')}. {it.get('tasks', '')}",
                    "tasks": it.get("tasks") or "",
                    "has_apply_button": True,
                },
                now_iso,
            )
        )
    if items:
        save_json(PRIVATE_GMAIL_QUEUE, {"items": []})
    return cards, len(cards)


def main():
    now_dt = datetime.now(timezone.utc)
    now_iso = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    existing_feed = load_json(FEED_PATH, {"meta": {}, "jobs": {}, "notification_log": {}, "audit_logs": []})
    notif_log = existing_feed.get("notification_log", {}) if isinstance(existing_feed, dict) else {}
    audit_logs = existing_feed.get("audit_logs", []) if isinstance(existing_feed, dict) else []

    raw_items, source_statuses, executed_queries = scrape_all_real_sources()
    scan_completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    gmail_cards, gmail_count = read_local_gmail_queue_if_present(now_iso)
    if gmail_count > 0:
        source_statuses["gmail_bridge"] = {"state": "OK", "label": f"تم استيعاب {gmail_count} تنبيه", "count": gmail_count}

    # Start clean on fresh 24h jobs only
    fresh_jobs = {}
    family_index = {}

    for raw_item in raw_items:
        pub_candidate = raw_item.get("first_published") or raw_item.get("discovered_at")
        if not is_within_last_24h(pub_candidate, now_dt):
            continue

        card = build_evaluated_card(raw_item, now_iso)
        if card["receipt"]["apply_state"] == "CLOSED":
            continue

        jid = card["id"]
        if jid in fresh_jobs:
            old = fresh_jobs[jid]
            old["sources"] = list(dict.fromkeys((old.get("sources") or []) + card["sources"]))
            old["all_urls"] = list(dict.fromkeys((old.get("all_urls") or []) + card["all_urls"]))
        else:
            fid = card.get("family_id")
            if fid and fid in family_index and family_index[fid] != jid:
                card["probable_duplicate_of"] = family_index[fid]
            elif fid:
                family_index[fid] = jid
            fresh_jobs[jid] = card

    for card in gmail_cards:
        jid = card["id"]
        fresh_jobs[jid] = card

    sorted_pairs = sorted(
        fresh_jobs.items(),
        key=lambda kv: (kv[1].get("fit", {}).get("score") or 0, kv[1].get("discovered_at", "")),
        reverse=True,
    )[:160]
    trimmed_jobs = dict(sorted_pairs)

    alert_candidates = []
    for jid, job in trimmed_jobs.items():
        if notif_log.get(jid, {}).get("status") == "ACCEPTED":
            continue
        fit = job.get("fit", {})
        rec = job.get("receipt", {})
        score = fit.get("score")
        if (
            score is not None
            and score >= PRIORITY_THRESHOLD
            and rec.get("apply_state") != "CLOSED"
            and not fit.get("has_mandatory_conflict")
        ):
            alert_candidates.append(job)

    alert_candidates.sort(
        key=lambda j: (
            j.get("fit", {}).get("score") or 0,
            1 if j.get("commute", {}).get("status") in ("CONFIRMED", "ESTIMATED") else 0,
        ),
        reverse=True,
    )

    feed_published_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    audit_logs.append({
        "completed_at": scan_completed_at,
        "published_at": feed_published_at,
        "queries_executed": executed_queries[:24],
        "total_fresh_24h": len(trimmed_jobs),
    })
    audit_logs = audit_logs[-12:]

    out_feed = {
        "meta": {
            "scan_completed_at": scan_completed_at,
            "feed_published_at": feed_published_at,
            "priority_threshold": PRIORITY_THRESHOLD,
            "fresh_window_hours": MAX_AGE_HOURS,
            "total_active": len(trimmed_jobs),
            "source_statuses": source_statuses,
        },
        "jobs": trimmed_jobs,
        "notification_log": notif_log,
        "audit_logs": audit_logs,
    }
    save_json(FEED_PATH, out_feed)

    ntfy_topic = os.environ.get("NTFY_TOPIC", "").strip()
    pwa_base_url = os.environ.get("PWA_BASE_URL", "").strip()
    for top_job in alert_candidates[:3]:
        jid = top_job["id"]
        delivery_status = send_ntfy_alert(top_job, ntfy_topic, pwa_base_url)
        notif_log[jid] = {
            "status": delivery_status,
            "status_ar": "الخدمة قبلت الإرسال" if delivery_status == "ACCEPTED" else f"فشل الإرسال ({delivery_status})",
            "attempted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    out_feed["notification_log"] = notif_log
    save_json(FEED_PATH, out_feed)
    print(f"Fresh 24h scan finished at {scan_completed_at}, count={len(trimmed_jobs)}.")


if __name__ == "__main__":
    main()
