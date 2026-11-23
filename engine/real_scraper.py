import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    from jobspy import scrape_jobs
    HAS_JOBSPY = True
except Exception:
    HAS_JOBSPY = False

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/129.0.0.0 Safari/537.36"
)

SENIOR_RX = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|head|director|vp|vice president|chief|manager|architect|expert|3\+\s*years|4\+\s*years|5\+\s*years|6\+\s*years)\b",
    re.I,
)

NEGATIVE_ROLE_RX = re.compile(
    r"\b(telesales|tele-sales|call center|customer service|customer support|door to door|outdoor sales|real estate|driver|security|nurse|pharmacist|chef|graphic designer|video editor|frontend|backend|fullstack|ios|android|flutter|devops|chinese speaker|german speaker|french speaker|spanish speaker)\b",
    re.I,
)

JOBSPY_TERMS = [
    "Data Analyst",
    "Business Intelligence Analyst",
    "Reporting Analyst",
    "Operations Analyst",
    "Business Analyst",
    "MIS Analyst",
]

LINKEDIN_QUERIES = [
    "Data Analyst",
    "Business Intelligence Analyst",
    "BI Analyst",
    "Reporting Analyst",
    "MIS Analyst",
    "SFE",
    "Sales Force Effectiveness",
    "Operations Analyst",
    "Business Analyst",
    "Systems Analyst",
    "Product Analyst",
    "Data Specialist",
    "SQL Power BI",
    "Excel Analyst",
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


def http_request(url, method="GET", payload=None, extra_headers=None, timeout=16):
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


def scrape_with_jobspy(now_iso):
    """Scrapes LinkedIn Egypt, Indeed Egypt, and Google Jobs simultaneously via python-jobspy ($0)."""
    if not HAS_JOBSPY:
        return []
    found = {}
    for term in JOBSPY_TERMS:
        try:
            df = scrape_jobs(
                site_name=["indeed", "linkedin", "google"],
                search_term=term,
                location="Cairo, Egypt",
                country_indeed="Egypt",
                results_wanted=25,
                hours_old=168,
            )
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                title = str(row.get("title") or "").strip()
                company = str(row.get("company") or "Employer in Egypt").strip()
                job_url = str(row.get("job_url") or "").strip()
                loc = str(row.get("location") or "Cairo, Egypt").strip()
                site = str(row.get("site") or "job_board").strip().lower()
                desc = strip_tags(str(row.get("description") or ""))[:450]
                date_posted = str(row.get("date_posted") or now_iso)[:10]

                if not job_url.startswith("http") or not is_relevant_entry_role(title, desc):
                    continue

                if "indeed" in site:
                    src_label = "Indeed Egypt"
                elif "linkedin" in site:
                    src_label = "LinkedIn Jobs (Egypt)"
                else:
                    src_label = "Google Jobs (Egypt)"

                found[job_url] = {
                    "company": company if company.lower() != "nan" else "شركة في مصر",
                    "title": title,
                    "location": loc if loc.lower() != "nan" else "Cairo, Egypt",
                    "work_mode": "Remote" if bool(row.get("is_remote")) else "Hybrid",
                    "source_name": src_label,
                    "url": job_url,
                    "first_published": date_posted if date_posted.lower() != "nan" else now_iso[:10],
                    "discovered_at": now_iso,
                    "required_text": f"{title} {desc}",
                    "tasks": desc or title,
                }
            time.sleep(0.5)
        except Exception:
            continue
    return list(found.values())


def scrape_linkedin_egypt_guest(now_iso):
    """Fetches up to 40 results per keyword across 14 queries from LinkedIn Egypt public index."""
    found = {}
    for kw in LINKEDIN_QUERIES:
        encoded_kw = urllib.parse.quote(kw)
        for start in [0, 10, 20, 30]:
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
                time.sleep(0.3)
            except Exception:
                break
    return list(found.values())


def scrape_wuzzuf_egypt(now_iso):
    found = {}
    api_url = "https://wuzzuf.net/api/search/job"
    for kw in WUZZUF_QUERIES:
        try:
            payload = {"startIndex": 0, "pageSize": 30, "query": kw, "filters": {}}
            raw = http_request(
                api_url,
                method="POST",
                payload=payload,
                extra_headers={
                    "Accept": "application/vnd.api+json",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": "https://wuzzuf.net",
                    "Referer": "https://wuzzuf.net/search/jobs/",
                },
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
    js_jobs = scrape_with_jobspy(now_iso)
    li_jobs = scrape_linkedin_egypt_guest(now_iso)
    wz_jobs = scrape_wuzzuf_egypt(now_iso)
    co_jobs = scrape_egypt_company_boards(now_iso)
    rm_jobs = scrape_remotive_global(now_iso)

    raw_items = js_jobs + li_jobs + wz_jobs + co_jobs + rm_jobs

    indeed_cnt = sum(1 for j in js_jobs if "indeed" in j.get("source_name", "").lower())
    li_js_cnt = sum(1 for j in js_jobs if "linkedin" in j.get("source_name", "").lower())
    google_js_cnt = len(js_jobs) - indeed_cnt - li_js_cnt

    stats = {
        "linkedin_egypt": len(li_jobs) + li_js_cnt,
        "indeed_egypt": indeed_cnt + google_js_cnt,
        "wuzzuf_egypt": len(wz_jobs),
        "egypt_companies": len(co_jobs),
        "remotive_global": len(rm_jobs),
    }
    return raw_items, stats
