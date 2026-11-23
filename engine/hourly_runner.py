import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Point 13: Import matcher and run self-tests BEFORE evaluating or notifying
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


def send_ntfy_alert(job, ntfy_topic, pwa_base_url) -> Tuple_status := str:
    """Point 28, 29, 31, 32: Minimal PII payload, deep-link ?job=<id>, returns delivery status."""
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
    location = raw_item.get("location")  # None if unknown
    work_mode = raw_item.get("work_mode")  # None if unknown
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
        __import__("re").search(r"\b(intern|internship|trainee|graduate program|تدريب|متدرب)\b", f"{title} {raw_item.get('tasks', '')}", __import__("re").I)
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
        "location": location,  # None if missing (rendered as 'العنوان غير مذكور')
        "work_mode": work_mode,  # None if missing (rendered as 'غير محدد')
        "is_training": is_training,
        "receipt": receipt,
        "fit": fit,
        "commute": commute,
        "discovered_at": raw_item.get("discovered_at") or now_iso,
    }


def read_local_gmail_queue_if_present(now_iso):
    """Point 33: Reads local/private queue if available without ever committing it to public git."""
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
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing_feed = load_json(FEED_PATH, {"meta": {}, "jobs": {}, "notification_log": {}, "audit_logs": []})
    existing_jobs = existing_feed.get("jobs", {}) if isinstance(existing_feed, dict) else {}
    notif_log = existing_feed.get("notification_log", {}) if isinstance(existing_feed, dict) else {}
    audit_logs = existing_feed.get("audit_logs", []) if isinstance(existing_feed, dict) else []

    raw_items, source_statuses, executed_queries = scrape_all_real_sources()
    scan_completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    gmail_cards, gmail_count = read_local_gmail_queue_if_present(now_iso)
    if gmail_count > 0:
        source_statuses["gmail_bridge"] = {"state": "OK", "label": f"تم استيعاب {gmail_count} تنبيه", "count": gmail_count}

    incoming_cards = [build_evaluated_card(r, now_iso) for r in raw_items] + gmail_cards

    # Index existing family IDs to flag probable duplicates across different districts (Point 22)
    family_index = {}
    for eid, ejob in existing_jobs.items():
        fid = ejob.get("family_id")
        if fid and fid not in family_index:
            family_index[fid] = eid

    seen_in_this_run = set()

    for card in incoming_cards:
        jid = card["id"]
        seen_in_this_run.add(jid)

        if jid in existing_jobs:
            # Point 23: Re-evaluate existing card with fresh evidence (including CLOSED state)
            old = existing_jobs[jid]
            card["discovered_at"] = old.get("discovered_at") or card["discovered_at"]
            card["sources"] = list(dict.fromkeys((old.get("sources") or []) + card["sources"]))
            card["all_urls"] = list(dict.fromkeys((old.get("all_urls") or []) + card["all_urls"]))
            existing_jobs[jid] = card
        else:
            fid = card.get("family_id")
            if fid and fid in family_index and family_index[fid] != jid:
                card["probable_duplicate_of"] = family_index[fid]
            elif fid:
                family_index[fid] = jid
            existing_jobs[jid] = card

    # Point 23: Review older cards not seen in this run
    for jid, old in list(existing_jobs.items()):
        if jid not in seen_in_this_run:
            # Keep closed cards marked CLOSED so user sees status in 'تقديماتي'
            if old.get("receipt", {}).get("apply_state") == "CLOSED":
                continue

    # Keep top 160 active/recent items sorted by discovery & fit
    sorted_pairs = sorted(
        existing_jobs.items(),
        key=lambda kv: (
            1 if kv[1].get("receipt", {}).get("apply_state") != "CLOSED" else 0,
            kv[1].get("fit", {}).get("score") or 0,
            kv[1].get("discovered_at", ""),
        ),
        reverse=True,
    )[:160]
    trimmed_jobs = dict(sorted_pairs)

    # Point 19 & 30: Sort eligible candidates by (fit_score, verification_confidence) BEFORE selecting top 3 alerts
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
            and rec.get("apply_state") == "OPEN_VERIFIED"
            and rec.get("egypt_status") == "CONFIRMED"
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
        "queries_executed": executed_queries[:18],
        "total_evaluated": len(incoming_cards),
    })
    audit_logs = audit_logs[-12:]

    out_feed = {
        "meta": {
            "scan_completed_at": scan_completed_at,
            "feed_published_at": feed_published_at,
            "priority_threshold": PRIORITY_THRESHOLD,
            "total_active": len(trimmed_jobs),
            "source_statuses": source_statuses,
        },
        "jobs": trimmed_jobs,
        "notification_log": notif_log,
        "audit_logs": audit_logs,
    }
    # Publish feed BEFORE sending notifications so ?job=<id> is live immediately (Point 28)
    save_json(FEED_PATH, out_feed)

    # Point 29: Track ntfy delivery status independently of job ingestion & retry if previously failed
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
    print(f"Scan finished at {scan_completed_at}, published at {feed_published_at}, total={len(trimmed_jobs)}.")


if __name__ == "__main__":
    main()
