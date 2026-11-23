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

LINKEDIN_JOB_QUERIES = [
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
    "Sales Support Reporting",
]

JOBSPY_QUERIES = [
    "Data Analyst",
    "Business Intelligence Analyst",
    "Reporting Analyst",
    "Operations Analyst",
    "Business Analyst",
    "MIS Analyst",
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
        return resp.status, resp.read().decode("utf-8", errors="ignore")


def strip_tags(raw_html):
    text = re.sub(r"<[^>]+>", " ", str(raw_html or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def clean_field(val) -> Optional_str := None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "unknown"):
        return None
    return s


def scrape_linkedin_jobs_egypt(now_iso):
    found = {}
    errors = 0
    for kw in LINKEDIN_JOB_QUERIES:
        encoded_kw = urllib.parse.quote(kw)
        for start in [0, 10, 20]:
            url = (
                f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={encoded_kw}&location=Egypt&f_TPR=r604800&start={start}"
            )
            try:
                status, body = http_request(url, timeout=14)
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
                    company = strip_tags(comp_m.group(1)) if comp_m else None
                    loc = strip_tags(loc_m.group(1)) if loc_m else None
                    clean_url = link_m.group(1).strip()
                    pub_date = time_m.group(1).strip() if time_m else None

                    found[clean_url] = {
                        "company": company or "جهة معلنة على LinkedIn",
                        "title": title,
                        "location": loc,  # None if missing (Point 15)
                        "work_mode": "Remote" if (loc and "remote" in loc.lower()) else None,
                        "source_name": "LinkedIn Jobs",
                        "source_category": "job_board",
                        "url": clean_url,
                        "http_status": status,
                        "has_apply_button": True,
                        "first_published": pub_date,
                        "discovered_at": now_iso,
                        "required_text": title,
                        "tasks": "",
                    }
                time.sleep(0.3)
            except Exception:
                errors += 1
                break

    items = list(found.values())
    if items:
        src_status = {"state": "OK", "label": f"نجح ({len(items)} إعلان)", "count": len(items)}
    elif errors > 0:
        src_status = {"state": "FAILED", "label": "تعذّر الاتصال مؤقتًا", "count": 0}
    else:
        src_status = {"state": "OK_ZERO", "label": "نجح وجاب ٠", "count": 0}
    return items, src_status


def scrape_jobspy_indeed_google(now_iso):
    if not HAS_JOBSPY:
        return [], {"state": "UNCONFIGURED", "label": "المكتبة غير مثبتة", "count": 0}

    found = {}
    errors = 0
    for term in JOBSPY_QUERIES:
        try:
            df = scrape_jobs(
                site_name=["indeed", "google"],
                search_term=term,
                location="Cairo, Egypt",
                country_indeed="Egypt",
                results_wanted=20,
                hours_old=168,
            )
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                title = clean_field(row.get("title"))
                job_url = clean_field(row.get("job_url"))
                if not title or not job_url or not job_url.startswith("http"):
                    continue
                company = clean_field(row.get("company")) or "جهة معلنة"
                loc = clean_field(row.get("location"))
                site = (clean_field(row.get("site")) or "indeed").lower()
                desc = strip_tags(clean_field(row.get("description")) or "")[:700]
                date_posted = clean_field(row.get("date_posted"))
                is_remote = bool(row.get("is_remote")) if row.get("is_remote") is not None else None

                found[job_url] = {
                    "company": company,
                    "title": title,
                    "location": loc,
                    "work_mode": "Remote" if is_remote else None,
                    "source_name": "Indeed Egypt" if "indeed" in site else "Google Jobs",
                    "source_category": "job_board",
                    "url": job_url,
                    "http_status": 200,
                    "has_apply_button": True,
                    "first_published": date_posted,
                    "discovered_at": now_iso,
                    "required_text": f"{title}. {desc}",
                    "tasks": desc,
                }
            time.sleep(0.4)
        except Exception:
            errors += 1
            continue

    items = list(found.values())
    if items:
        src_status = {"state": "OK", "label": f"نجح ({len(items)} إعلان)", "count": len(items)}
    elif errors > 0:
        src_status = {"state": "FAILED", "label": "تعذّر السحب", "count": 0}
    else:
        src_status = {"state": "OK_ZERO", "label": "نجح وجاب ٠", "count": 0}
    return items, src_status


def scrape_public_hiring_posts(now_iso):
    """Point 24: Dedicated Hiring Posts source searching public Arabic & English HR posts."""
    queries = [
        'site:linkedin.com/posts ("Data Analyst" OR "BI Analyst" OR "SFE" OR "Commercial Excellence" OR "MIS") ("Cairo" OR "Egypt")',
        'site:linkedin.com/posts ("مطلوب فريش" OR "ابعت الـCV" OR "تحليل بيانات" OR "تقارير") ("القاهرة" OR "مصر")',
    ]
    found = {}
    errors = 0
    for q in queries:
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(q)}"
            status, body = http_request(ddg_url, timeout=15)
            blocks = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, flags=re.S)
            for href, raw_t in blocks:
                if "uddg=" in href:
                    m = re.search(r"uddg=([^&]+)", href)
                    if m:
                        href = urllib.parse.unquote(m.group(1))
                if not href.startswith("http"):
                    continue
                title = strip_tags(raw_t)
                found[href] = {
                    "company": "بوست توظيف عام",
                    "title": title[:110],
                    "location": "مصر" if ("egypt" in title.lower() or "مصر" in title or "القاهرة" in title) else None,
                    "work_mode": None,
                    "source_name": "بوستات التوظيف",
                    "source_category": "hiring_posts",
                    "url": href,
                    "http_status": status,
                    "has_apply_button": False,
                    "first_published": None,
                    "discovered_at": now_iso,
                    "required_text": title,
                    "tasks": title,
                }
            time.sleep(0.5)
        except Exception:
            errors += 1
            continue

    items = list(found.values())
    if items:
        src_status = {"state": "OK", "label": f"نجح ({len(items)} بوست)", "count": len(items)}
    elif errors > 0:
        src_status = {"state": "FAILED", "label": "تعذّر الوصول للبوستات", "count": 0}
    else:
        src_status = {"state": "OK_ZERO", "label": "نجح وجاب ٠", "count": 0}
    return items, src_status


def scrape_egypt_company_boards(now_iso):
    results = []
    errors = 0
    for company, slug in WORKABLE_COMPANIES:
        api_url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
        try:
            status, raw = http_request(api_url, method="GET", extra_headers={"Accept": "application/json"}, timeout=12)
            data = json.loads(raw)
            for job in data.get("jobs", []):
                title = clean_field(job.get("title"))
                if not title:
                    continue
                city = clean_field(job.get("city"))
                country = clean_field(job.get("country"))
                loc_str = ", ".join([x for x in [city, country] if x]) or None
                is_remote = bool(job.get("telecommuting"))
                if country and "egypt" not in country.lower() and not is_remote:
                    continue
                shortcode = clean_field(job.get("shortcode"))
                job_url = clean_field(job.get("url")) or (
                    f"https://apply.workable.com/{slug}/j/{shortcode}/" if shortcode else f"https://apply.workable.com/{slug}/"
                )
                results.append({
                    "company": company,
                    "title": title,
                    "location": loc_str,
                    "work_mode": "Remote" if is_remote else None,
                    "source_name": f"{company} Careers",
                    "source_category": "company_portal",
                    "url": job_url,
                    "http_status": status,
                    "has_apply_button": bool(shortcode),
                    "first_published": clean_field(job.get("published_on")),
                    "discovered_at": now_iso,
                    "required_text": title,
                    "tasks": "",
                })
        except Exception:
            errors += 1
            continue

    if results:
        src_status = {"state": "OK", "label": f"نجح ({len(results)} وظيفة)", "count": len(results)}
    elif errors == len(WORKABLE_COMPANIES):
        src_status = {"state": "FAILED", "label": "تعذّر الاتصال ببوابات الشركات", "count": 0}
    else:
        src_status = {"state": "OK_ZERO", "label": "نجح وجاب ٠", "count": 0}
    return results, src_status


def scrape_remotive_global(now_iso):
    results = []
    errors = 0
    for cat in ["data", "business"]:
        try:
            status, raw = http_request(f"https://remotive.com/api/remote-jobs?category={cat}&limit=30", timeout=14)
            data = json.loads(raw)
            for job in data.get("jobs", []):
                title = clean_field(job.get("title"))
                if not title:
                    continue
                req_loc = clean_field(job.get("candidate_required_location"))
                desc = strip_tags(clean_field(job.get("description")) or "")[:600]
                results.append({
                    "company": clean_field(job.get("company_name")) or "شركة ريموت",
                    "title": title,
                    "location": req_loc,
                    "eligible_regions": req_loc or "",
                    "work_mode": "Remote",
                    "source_name": "Remotive",
                    "source_category": "remote_board",
                    "url": clean_field(job.get("url")) or "https://remotive.com",
                    "http_status": status,
                    "has_apply_button": True,
                    "first_published": clean_field(job.get("publication_date")),
                    "discovered_at": now_iso,
                    "required_text": f"{title}. {desc}",
                    "tasks": desc,
                })
        except Exception:
            errors += 1
            continue

    if results:
        src_status = {"state": "OK", "label": f"نجح ({len(results)} وظيفة)", "count": len(results)}
    elif errors > 0:
        src_status = {"state": "FAILED", "label": "تعذّر الاتصال", "count": 0}
    else:
        src_status = {"state": "OK_ZERO", "label": "نجح وجاب ٠", "count": 0}
    return results, src_status


def scrape_all_real_sources():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    li_items, li_status = scrape_linkedin_jobs_egypt(now_iso)
    ig_items, ig_status = scrape_jobspy_indeed_google(now_iso)
    hp_items, hp_status = scrape_public_hiring_posts(now_iso)
    co_items, co_status = scrape_egypt_company_boards(now_iso)
    rm_items, rm_status = scrape_remotive_global(now_iso)

    raw_items = li_items + ig_items + hp_items + co_items + rm_items

    source_statuses = {
        "linkedin_jobs": li_status,
        "indeed_google": ig_status,
        "hiring_posts": hp_status,
        "egypt_companies": co_status,
        "remotive": rm_status,
        "wuzzuf": {"state": "EMAIL_ALERT_ONLY", "label": "مربوط عبر تنبيهات البريد", "count": 0},
        "gmail_bridge": {"state": "PRIVATE_QUEUE", "label": "خاص خارج المستودع العام", "count": 0},
    }

    executed_queries = LINKEDIN_JOB_QUERIES + JOBSPY_QUERIES
    return raw_items, source_statuses, executed_queries
