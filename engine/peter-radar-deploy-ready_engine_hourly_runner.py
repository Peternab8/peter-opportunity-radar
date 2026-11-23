import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "engine"))

from radar_v2 import (
    compute_job_identity,
    verify_receipt_and_status,
    evaluate_weekly_commute,
    evaluate_evidence_fit
)
from real_scraper import run_full_hourly_scrape, send_real_android_push_ntfy

LIVE_FEED_PATH = os.path.join(BASE_DIR, "data", "live_feed.json")
GMAIL_QUEUE_PATH = os.path.join(BASE_DIR, "data", "gmail_queue.json")
PWA_BASE_URL = os.environ.get("PWA_BASE_URL", "https://peternab8.github.io/peter-opportunity-radar/")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_hourly_cycle(offline_test_items=None):
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    feed = load_json(LIVE_FEED_PATH, {
        "meta": {
            "owner": "Peter Nabil Gerges",
            "last_successful_run": None,
            "total_runs": 0,
            "source_health": {}
        },
        "jobs": {},
        "search_audit_log": []
    })

    raw_items = []
    source_health = {
        "ats_career_pages": {"label": "بوابات الشركات (Paymob, Breadfast, Thndr...)", "status": "OK", "found": 0, "last_checked": now_iso},
        "linkedin_public_posts": {"label": "LinkedIn Public Jobs & Posts", "status": "OK", "found": 0, "last_checked": now_iso},
        "wuzzuf": {"label": "WUZZUF Entry-Level", "status": "OK", "found": 0, "last_checked": now_iso},
        "remote_apis": {"label": "Remotive & Himalayas Remote", "status": "OK", "found": 0, "last_checked": now_iso},
        "gmail_alerts_bridge": {"label": "Gmail Alerts Bridge (OAuth)", "status": "OK", "found": 0, "last_checked": now_iso}
    }

    if offline_test_items is not None:
        raw_items.extend(offline_test_items)
    else:
        try:
            scraped = run_full_hourly_scrape()
            raw_items.extend(scraped)
        except Exception as e:
            source_health["linkedin_public_posts"]["status"] = f"ERROR: {str(e)[:60]}"

    # Ingest any items pushed from Google Apps Script (Gmail Alerts)
    gmail_queue = load_json(GMAIL_QUEUE_PATH, {"items": []})
    if gmail_queue.get("items"):
        raw_items.extend(gmail_queue["items"])
        source_health["gmail_alerts_bridge"]["found"] = len(gmail_queue["items"])
        save_json(GMAIL_QUEUE_PATH, {"items": [], "last_flushed": now_iso})

    new_high_fit = []
    merged_count = 0
    closed_count = 0

    for item in raw_items:
        ch = item.get("source_channel", "ats_career_pages")
        if ch in source_health:
            source_health[ch]["found"] += 1

        receipt = verify_receipt_and_status(item, now_iso)
        if receipt["apply_state"] == "CLOSED":
            closed_count += 1
            continue

        exact_id, loose_id = compute_job_identity(
            item.get("company", "Unknown"),
            item.get("title", "Role"),
            item.get("req_id"),
            item.get("location")
        )

        if exact_id in feed["jobs"]:
            existing = feed["jobs"][exact_id]
            src_name = item.get("source_name", ch)
            if src_name not in existing["sources"]:
                existing["sources"].append(src_name)
            if item.get("url") and item["url"] not in existing["all_urls"]:
                existing["all_urls"].append(item["url"])
            existing["receipt"]["last_verified"] = now_iso
            merged_count += 1
            continue

        fit = evaluate_evidence_fit(item)
        commute = evaluate_weekly_commute(
            item.get("location"),
            item.get("work_mode"),
            item.get("onsite_days_per_week"),
            item.get("company_shuttle")
        )

        card = {
            "id": exact_id,
            "family_id": loose_id,
            "company": item.get("company", "غير محدد"),
            "title": item.get("title", "غير محدد"),
            "sources": [item.get("source_name", ch)],
            "all_urls": [item["url"]] if item.get("url") else [],
            "primary_url": item.get("resolved_apply_url") or item.get("url") or "",
            "location": item.get("location") or "غير مذكور",
            "work_mode": item.get("work_mode") or "غير مذكور",
            "salary": item.get("salary"),
            "receipt": receipt,
            "fit": fit,
            "commute": commute,
            "discovered_at": now_iso
        }
        feed["jobs"][exact_id] = card

        score = fit.get("score") or 0
        if score >= 80:
            new_high_fit.append(card)
            if NTFY_TOPIC:
                deep_link = f"{PWA_BASE_URL.rstrip('/')}/?job_id={exact_id}"
                commute_txt = "المشوار محتاج تحقق" if commute["status"] != "CONFIRMED" else f"المشوار {commute['score']}%"
                send_real_android_push_ntfy(
                    topic=NTFY_TOPIC,
                    title=f"{card['title']} @ {card['company']} | Fit {score}%",
                    body=f"{fit['summary']} | {commute_txt}",
                    click_url=deep_link
                )

    feed["meta"]["last_successful_run"] = now_iso
    feed["meta"]["total_runs"] = feed["meta"].get("total_runs", 0) + 1
    feed["meta"]["source_health"] = source_health
    feed["search_audit_log"].append({
        "run_id": f"run_{feed['meta']['total_runs']}",
        "completed_at": now_iso,
        "raw_fetched": len(raw_items),
        "new_high_fit": len(new_high_fit),
        "merged_duplicates": merged_count,
        "closed_filtered": closed_count,
        "queries_executed": [
            '"Data Analyst" Cairo', '"BI Analyst" Egypt', '"Reporting Analyst" Cairo',
            '"MIS" Egypt', '"SFE" Egypt', '"Sales Force Effectiveness" Cairo',
            '"Sales Operations" Egypt', '"Business Analyst" Cairo', '"Operations Analyst" Egypt'
        ]
    })
    feed["search_audit_log"] = feed["search_audit_log"][-50:]
    save_json(LIVE_FEED_PATH, feed)
    return {
        "completed_at": now_iso,
        "raw_fetched": len(raw_items),
        "total_jobs_in_feed": len(feed["jobs"]),
        "new_high_fit": len(new_high_fit),
        "merged_duplicates": merged_count,
        "closed_filtered": closed_count
    }


if __name__ == "__main__":
    summary = run_hourly_cycle()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
