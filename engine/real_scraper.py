import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)

SENIOR_RX = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|head|director|vp|vice president|chief|manager|architect|expert|3\+\s*years|4\+\s*years|5\+\s*years)\b",
    re.I,
)

NEGATIVE_ROLE_RX = re.compile(
    r"\b(telesales|tele-sales|call center|customer service|customer support|door to door|outdoor sales|real estate|driver|security|nurse|pharmacist|chef|graphic designer|video editor|frontend|backend|fullstack|ios|android|flutter|devops)\b",
    re.I,
)

LINKEDIN_QUERIES = [
    "Data Analyst",
    "Business Intelligence Analyst",
    "Reporting Analyst",
    "MIS Analyst",
    "SFE",
    "Sales Force Effectiveness",
    "Operations Analyst",
    "Business Analyst",
    "Systems Analyst",
    "SQL Power BI",
]

WUZZUF_QUERIES = [
    "data analyst",
    "business intelligence",
    "reporting analyst",
    "mis",
    "operations analyst",
    "business analyst",
]

WORKABLE_COMPANIES = [
    ("Paymob", "paymob"),
    ("Breadfast", "breadfast"),
    ("Bosta", "bosta"),
    ("MaxAB", "maxab"),
    ("Thndr", "thndr"),
    ("Khazna", "khazna"),
    ("Rabbit", "rabbit"),
    ("MNT-Halan", "mnzl"),
    ("MoneyFellows", "moneyfellows"),
    ("Telda", "telda"),
    ("Yodawy", "yodawy"),
    ("Vezeeta", "vezeeta"),
    ("Homzmart", "homzmart"),
    ("Instabug", "instabug"),
    ("Swvl", "swvl"),
    ("Trella", "trella"),
    ("Fawry", "fawry"),
    ("ValU", "valu"),
]


def http_request(url, method="GET", payload=None, extra_headers=None, timeout=20):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def strip_tags(raw_html):
    text = re.sub(r"<[^>]+>", " ", str(raw_html or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def is_relevant_entry_role(title, extra_text=""):
    t = str(title or "")
    if not t or SENIOR_RX.search(t) or NEGATIVE_ROLE_RX.search(t):
        return False
    combined = f"{t} {extra_text}".lower()
    return bool(
        re.search(
            r"\b(data|bi|business intelligence|reporting|mis|sfe|sales force|operations analyst|business analyst|analytics|product analyst|systems analyst|sql|power bi|excel|tableau)\b",
            combined,
            re.I,
        )
    )


def search_web_via_gemini_grounding(now_iso):
    """Uses Gemini 2.5 Flash + Google Search Grounding and returns (jobs_list, status_string)."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return [], "غير مفعّل (GEMINI_API_KEY غير موجود في Secrets)"

    prompts = [
        (
            "Use Google Search right now to find the newest entry-level, junior, fresh graduate, or internship job postings "
            "and HR posts in Egypt (Cairo / Giza / Remote Egypt) from the last 7 days for: "
            "Data Analyst, Business Intelligence Analyst, Reporting Analyst, MIS Analyst, SFE (Sales Force Effectiveness), "
            "or Operations Analyst across site:linkedin.com/posts, site:linkedin.com/jobs, site:wuzzuf.net, and site:eg.indeed.com. "
            "Exclude Senior, Lead, Manager, or Director roles. "
            "Return ONLY a JSON array of up to 18 real opportunities with keys: "
            "title, company, location, source, url, tasks_summary."
        ),
        (
            "Use Google Search right now to find graduate programs, data trainee, commercial operations analyst, "
            "or BI specialist openings in Egyptian fintech, telecom, banks, and e-commerce companies (Paymob, Fawry, CIB, "
            "Vodafone VOIS, e&, Raya, Breadfast, Bosta, Talabat, MaxAB, Noon, Jumia) in Cairo Egypt from the past 7 days. "
            "Exclude Senior/Manager roles. "
            "Return ONLY a JSON array of up to 15 real opportunities with keys: title, company, location, source, url, tasks_summary."
        ),
    ]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={urllib.parse.quote(api_key)}"
    collected = []
    last_error = None

    for prompt in prompts:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        }
        try:
            raw = http_request(url, method="POST", payload=payload, timeout=30)
            parsed = json.loads(raw)
            cand = parsed["candidates"][0]
            text = cand["content"]["parts"][0].get("text", "")

            g_meta = cand.get("groundingMetadata") or {}
            grounding_urls = [
                (c.get("web") or {}).get("uri")
                for c in (g_meta.get("groundingChunks") or [])
                if (c.get("web") or {}).get("uri")
            ]

            json_m = re.search(r"\[[\s\S]*\]", text)
            if not json_m:
                last_error = "Gemini لم يُرجع مصفوفة JSON"
                continue
            items = json.loads(json_m.group(0))
            for idx, it in enumerate(items):
                if not isinstance(it, dict):
                    continue
                title = str(it.get("title") or "").strip()
                company = str(it.get("company") or "شركة في مصر").strip()
                if not title or SENIOR_RX.search(title):
                    continue
                loc = str(it.get("location") or "Cairo, Egypt").strip()
                src = str(it.get("source") or "Gemini Google Search").strip()
                tasks = str(it.get("tasks_summary") or f"{title} SQL Power BI Excel").strip()
                job_url = str(it.get("url") or "").strip()
                if not job_url.startswith("http"):
                    job_url = (
                        grounding_urls[idx]
                        if idx < len(grounding_urls)
                        else f"https://www.google.com/search?q={urllib.parse.quote(title + ' ' + company + ' Egypt')}"
                    )
                collected.append({
                    "company": company,
                    "title": title,
                    "location": loc,
                    "work_mode": "Remote" if "remote" in loc.lower() else "Hybrid",
                    "source_name": f"✨ {src}",
                    "url": job_url,
                    "first_published": now_iso[:10],
                    "discovered_at": now_iso,
                    "required_text": f"{title} {tasks}",
                    "tasks": tasks,
                })
        except Exception as exc:
            last_error = str(exc)[:110]
            continue

    if collected:
        return collected, f"شغّال ✓ ({len(collected)} فرصة)"
    return [], f"0 نتائج ({last_error or 'لم يجد نتائج جديدة'})"


def scrape_linkedin_egypt_guest(now_iso):
    found = {}
    for kw in LINKEDIN_QUERIES:
        encoded_kw = urllib.parse.quote(kw)
        for start in [0, 10]:
            url = (
                f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={encoded_kw}&location=Egypt&f_TPR=r604800&start={start}"
            )
            try:
                body = http_request(url, timeout=14)
                cards = re.findall(r"<li[^>]*>(.*?)</li>", body, flags=re.S)
                if not cards:
                    break
                for card in cards:
                    title_m = re.search(r'class="base-search-card__title[^"]*"[^>]*>(.*?)</', card, re.S)
                    comp_m = re.search(r'class="base-search-card__subtitle[^"]*"[^>]*>(.*?)</', card, re.S)
                    loc_m = re.search(r'class="job-search-card__location[^"]*"[^>]*>(.*?)</', card, re.S)
                    link_m = re.search(r'href="(https://[^"]*linkedin\.com/jobs/view/[^"?]+)', card)
                    time_m = re.search(r'<time[^>]*datetime="([^"]+)"', card)
                    if not title_m or not link_m:
                        continue
                    title = strip_tags(title_m.group(1))
                    company = strip_tags(comp_m.group(1)) if comp_m else "LinkedIn Employer"
                    loc = strip_tags(loc_m.group(1)) if loc_m else "Cairo, Egypt"
                    clean_url = link_m.group(1).strip()
                    pub_date = time_m.group(1)[:10] if time_m else now_iso[:10]

                    if not is_relevant_entry_role(title):
                        continue

                    found[clean_url] = {
                        "company": company,
                        "title": title,
                        "location": loc,
                        "work_mode": "Remote" if "remote" in loc.lower() else "Hybrid",
                        "source_name": "LinkedIn Jobs (Egypt)",
                        "url": clean_url,
                        "first_published": pub_date,
                        "discovered_at": now_iso,
                        "required_text": f"{title} SQL Excel Power BI",
                        "tasks": title,
                    }
                time.sleep(0.4)
            except Exception:
                break
    return list(found.values())


def scrape_wuzzuf_egypt(now_iso):
    found = {}
    api_url = "https://wuzzuf.net/api/search/job"
    for kw in WUZZUF_QUERIES:
        try:
            payload = {"startIndex": 0, "pageSize": 25, "query": kw, "filters": {}}
            raw = http_request(
                api_url,
                method="POST",
                payload=payload,
                extra_headers={"Accept": "application/json", "Referer": "https://wuzzuf.net/search/jobs/"},
                timeout=15,
            )
            data = json.loads(raw)
            for item in data.get("data", []):
                attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else item
                title = strip_tags(attrs.get("title") or "")
                desc = strip_tags(attrs.get("description") or attrs.get("requirements") or "")
                if not is_relevant_entry_role(title, desc):
                    continue
                comp_obj = attrs.get("company") or {}
                company = strip_tags(comp_obj.get("name") if isinstance(comp_obj, dict) else "شركة على WUZZUF")
                loc_obj = attrs.get("location") or {}
                city = loc_obj.get("city", {}).get("name", "") if isinstance(loc_obj.get("city"), dict) else ""
                area = loc_obj.get("area", {}).get("name", "") if isinstance(loc_obj.get("area"), dict) else ""
                loc = ", ".join([x for x in [area, city, "Egypt"] if x]) or "Cairo, Egypt"
                slug = attrs.get("slug") or item.get("id") or ""
                job_url = f"https://wuzzuf.net/jobs/p/{slug}" if slug else "https://wuzzuf.net/search/jobs/"

                found[job_url] = {
                    "company": company or "شركة على WUZZUF",
                    "title": title,
                    "location": loc,
                    "work_mode": "Hybrid",
                    "source_name": "WUZZUF",
                    "url": job_url,
                    "first_published": str(attrs.get("postedAt") or now_iso)[:10],
                    "discovered_at": now_iso,
                    "required_text": f"{title} {desc[:400]}",
                    "tasks": desc[:400] or title,
                }
            time.sleep(0.35)
        except Exception:
            continue
    return list(found.values())


def scrape_egypt_company_boards(now_iso):
    results = []
    for company, slug in WORKABLE_COMPANIES:
        api_url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
        try:
            raw = http_request(api_url, method="GET", extra_headers={"Accept": "application/json"}, timeout=12)
            data = json.loads(raw)
            for job in data.get("jobs", []):
                title = job.get("title", "")
                city = job.get("city") or ""
                country = job.get("country") or ""
                loc_str = f"{city}, {country}".strip(", ") or "Cairo, Egypt"
                is_remote = bool(job.get("telecommuting"))
                if country and "egypt" not in country.lower() and not is_remote:
                    continue
                if not is_relevant_entry_role(title):
                    continue
                shortcode = job.get("shortcode", "")
                job_url = job.get("url") or (f"https://apply.workable.com/{slug}/j/{shortcode}/" if shortcode else f"https://apply.workable.com/{slug}/")
                results.append({
                    "company": company,
                    "title": title,
                    "location": loc_str,
                    "work_mode": "Remote" if is_remote else "Hybrid",
                    "source_name": f"{company} Careers Portal",
                    "url": job_url,
                    "first_published": str(job.get("published_on") or now_iso)[:10],
                    "discovered_at": now_iso,
                    "required_text": f"{title} SQL Power BI Excel Python",
                    "tasks": title,
                })
        except Exception:
            continue
    return results


def scrape_remotive_global(now_iso):
    results = []
    for cat in ["data", "business"]:
        try:
            raw = http_request(f"https://remotive.com/api/remote-jobs?category={cat}&limit=30", timeout=14)
            data = json.loads(raw)
            for job in data.get("jobs", []):
                title = job.get("title", "")
                req_loc = job.get("candidate_required_location", "")
                if not re.search(r"\b(worldwide|anywhere|emea|egypt|middle east|africa)\b", req_loc, re.I):
                    continue
                desc = strip_tags(job.get("description", ""))[:400]
                if not is_relevant_entry_role(title, desc):
                    continue
                results.append({
                    "company": job.get("company_name", "Remote Company"),
                    "title": title,
                    "location": f"Remote ({req_loc})",
                    "work_mode": "Remote",
                    "source_name": "Remotive Live API",
                    "url": job.get("url", "https://remotive.com"),
                    "first_published": (job.get("publication_date") or now_iso)[:10],
                    "discovered_at": now_iso,
                    "required_text": f"{title} {desc}",
                    "tasks": desc,
                })
        except Exception:
            continue
    return results


def scrape_all_real_sources():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ai_jobs, gemini_status = search_web_via_gemini_grounding(now_iso)
    li_jobs = scrape_linkedin_egypt_guest(now_iso)
    wz_jobs = scrape_wuzzuf_egypt(now_iso)
    co_jobs = scrape_egypt_company_boards(now_iso)
    rm_jobs = scrape_remotive_global(now_iso)

    raw_items = ai_jobs + li_jobs + wz_jobs + co_jobs + rm_jobs
    stats = {
        "ai_google_search": len(ai_jobs),
        "gemini_status": gemini_status,
        "linkedin_egypt": len(li_jobs),
        "wuzzuf_egypt": len(wz_jobs),
        "egypt_companies": len(co_jobs),
        "remotive_global": len(rm_jobs),
    }
    return raw_items, stats
