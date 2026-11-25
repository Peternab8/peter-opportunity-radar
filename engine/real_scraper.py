import html
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
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

# Strict exclusion for senior/leadership/multi-year roles and non-target tracks
UNWANTED_ROLE_RX = re.compile(
    r"\b("
    r"senior|sr\.?|lead|principal|staff|head\s+of|director|vp|vice\s+president|manager|mgr|"
    r"architect|3\+\s*years?|4\+\s*years?|5\+\s*years?|6\+\s*years?|7\+\s*years?|"
    r"3\s*-\s*5\s*years?|4\s*-\s*6\s*years?|5\s*-\s*8\s*years?|"
    r"telesales|tele-sales|call\s+center|customer\s+service\s+representative|door\s+to\s+door|"
    r"outdoor\s+sales|field\s+sales|real\s+estate|broker|driver|security|nurse|pharmacist|chef|"
    r"graphic\s+designer|video\s+editor|copywriter|content\s+writer|"
    r"frontend|front-end|backend|back-end|fullstack|full-stack|devops|sre|"
    r"ios\s+developer|android\s+developer|flutter|react\s+native|software\s+engineer|"
    r"accountant|bookkeeper|auditor|tax\s+specialist|payroll\s+specialist"
    r")\b",
    re.I,
)

# Positive signal for Peter's CV tracks (Data, BI, Reporting, MIS, BA/SA, SFE, Operations)
TARGET_FIT_RX = re.compile(
    r"\b("
    r"data\s+analyst|data\s+analytics|business\s+intelligence|\bbi\b|power\s*bi|tableau|"
    r"reporting|mis\b|management\s+information|business\s+analyst|systems\s+analyst|"
    r"operations\s+analyst|business\s+operations|sfe|sales\s+force\s+effectiveness|"
    r"commercial\s+excellence|sales\s+analyst|sales\s+support|performance\s+analyst|"
    r"data\s+quality|data\s+management|sql|excel|python|kpi|dashboard|intern|internship|trainee|junior|entry\s+level|fresh"
    r")\b|تحليل\s+بيانات|بيانات|تقارير|مؤشرات|تشغيل|نظم|أعمال|فريش|تدريب",
    re.I,
)

LINKEDIN_JOB_QUERIES = [
    "Junior Reporting Analyst",
    "Reporting Analyst",
    "MIS Analyst",
    "Junior BI Analyst",
    "Business Intelligence Analyst",
    "Junior Data Analyst",
    "Data Analyst",
    "Junior Business Analyst",
    "Performance Analyst",
    "Data Quality Analyst",
    "Junior Systems Analyst",
    "Operations Analyst",
    "Sales Support Analyst",
    "Junior SFE Analyst",
    "Sales Force Effectiveness",
    "Sales Analyst",
    "Business Process Analyst",
    "Data Management Analyst",
]

JOBSPY_QUERIES = [
    "Reporting Analyst",
    "MIS Analyst",
    "Junior BI Analyst",
    "Data Analyst",
    "Business Analyst",
    "Operations Analyst",
    "Sales Support Analyst",
    "Junior SFE Analyst",
]

HIRING_POST_QUERIES = [
    'site:linkedin.com/posts ("hiring" OR "we are hiring" OR "send your cv" OR "send cv" OR "dm me") ("data analyst" OR "bi analyst" OR "business intelligence" OR "reporting" OR "mis" OR "sfe") ("junior" OR "fresh" OR "entry" OR "intern") ("egypt" OR "cairo" OR "giza")',
    'site:linkedin.com/posts ("fresh" OR "junior" OR "entry level" OR "intern" OR "internship" OR "graduate" OR "0-1") ("data" OR "bi" OR "analytics" OR "business analyst" OR "operations" OR "reporting") ("egypt" OR "cairo")',
    'site:linkedin.com/posts ("مطلوب" OR "فرصة عمل" OR "توظيف" OR "ابعت" OR "سي في" OR "cv") ("بيانات" OR "تحليل" OR "تقارير" OR "data" OR "bi" OR "excel" OR "sql") ("مصر" OR "القاهرة" OR "الجيزة")',
    '("send your cv" OR "send cv" OR "hiring") ("junior" OR "entry level" OR "fresh") ("data analyst" OR "bi analyst" OR "reporting analyst" OR "mis analyst" OR "sfe") ("cairo" OR "egypt")',
]

COMMUNITY_RSS_FEEDS = [
    ("بوستات المجتمع (Reddit Egypt)", "https://www.reddit.com/r/Egypt/search.rss?q=hiring+OR+job+OR+data+OR+analyst+OR+%D8%AA%D9%88%D8%B8%D9%8A%D9%81+OR+%D8%B4%D8%BA%D9%84&restrict_sr=on&sort=new"),
    ("بوستات البيانات (Reddit Data)", "https://www.reddit.com/r/dataanalysis/search.rss?q=junior+OR+entry+OR+intern+OR+hiring+OR+reporting&restrict_sr=on&sort=new"),
    ("بوستات BI (Reddit BI)", "https://www.reddit.com/r/BusinessIntelligence/search.rss?q=junior+OR+entry+OR+intern+OR+hiring+OR+power+bi&restrict_sr=on&sort=new"),
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


def clean_field(val):
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "unknown"):
        return None
    return s


def should_keep_role(title, extra_text=""):
    combined = f"{title or ''} {extra_text or ''}".strip()
    if not combined:
        return False
    if UNWANTED_ROLE_RX.search(combined):
        return False
    return bool(TARGET_FIT_RX.search(combined))


def extract_contact_or_apply_link(text, fallback_url):
    txt = str(text or "")
    email_m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
    if email_m:
        email_addr = email_m.group(0)
        return f"mailto:{email_addr}", email_addr
    form_m = re.search(
        r"https?://(?:forms\.gle|docs\.google\.com/forms|airtable\.com|typeform\.com|lnkd\.in)/\S+",
        txt,
    )
    if form_m:
        return form_m.group(0).rstrip(").,;"), None
    return fallback_url, None


def infer_location_and_mode(text):
    t = str(text or "")
    low = t.lower()

    loc = None
    for place, ar_name in [
        ("maadi", "المعادي، القاهرة"),
        ("dokki", "الدقي، الجيزة"),
        ("new cairo", "القاهرة الجديدة"),
        ("fifth settlement", "التجمع الخامس"),
        ("smart village", "القرية الذكية"),
        ("october", "٦ أكتوبر"),
        ("cairo", "القاهرة"),
        ("giza", "الجيزة"),
        ("egypt", "مصر"),
    ]:
        if place in low:
            loc = ar_name
            break

    if not loc:
        for ar_place, ar_label in [
            ("المعادي", "المعادي، القاهرة"),
            ("الدقي", "الدقي، الجيزة"),
            ("التجمع", "التجمع الخامس"),
            ("القاهرة الجديدة", "القاهرة الجديدة"),
            ("أكتوبر", "٦ أكتوبر"),
            ("القاهرة", "القاهرة"),
            ("الجيزة", "الجيزة"),
            ("مصر", "مصر"),
        ]:
            if ar_place in t:
                loc = ar_label
                break

    mode = None
    if "remote" in low or "عن بعد" in t or "ريموت" in t:
        mode = "Remote"
    elif "hybrid" in low or "هايبرد" in t:
        mode = "Hybrid"
    elif "onsite" in low or "on-site" in low or "من المقر" in t:
        mode = "On-site"

    return loc, mode


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
                    if not should_keep_role(title, kw):
                        continue
                    company = strip_tags(comp_m.group(1)) if comp_m else None
                    loc = strip_tags(loc_m.group(1)) if loc_m else None
                    clean_url = link_m.group(1).strip()
                    pub_date = time_m.group(1).strip() if time_m else None

                    found[clean_url] = {
                        "company": company or "جهة معلنة على LinkedIn",
                        "title": title,
                        "location": loc,
                        "work_mode": "Remote" if (loc and "remote" in loc.lower()) else None,
                        "source_name": "LinkedIn Jobs",
                        "source_category": "job_board",
                        "url": clean_url,
                        "http_status": status,
                        "has_apply_button": True,
                        "first_published": pub_date,
                        "discovered_at": now_iso,
                        "required_text": f"{title}. {kw}",
                        "tasks": "",
                    }
                time.sleep(0.25)
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
                desc = strip_tags(clean_field(row.get("description")) or "")[:700]
                if not should_keep_role(title, f"{term} {desc}"):
                    continue
                company = clean_field(row.get("company")) or "جهة معلنة"
                loc = clean_field(row.get("location"))
                site = (clean_field(row.get("site")) or "indeed").lower()
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
            time.sleep(0.35)
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


def scrape_hiring_posts(now_iso):
    found = {}
    errors = 0

    for q in HIRING_POST_QUERIES:
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
                if not should_keep_role(title, q):
                    continue
                loc, mode = infer_location_and_mode(title)
                target_url, extracted_email = extract_contact_or_apply_link(title, href)
                found[href] = {
                    "company": "بوست توظيف (LinkedIn)",
                    "title": title[:125],
                    "location": loc,
                    "work_mode": mode,
                    "source_name": "بوستات التوظيف",
                    "source_category": "hiring_posts",
                    "url": target_url,
                    "post_url": href,
                    "apply_email": extracted_email,
                    "http_status": status,
                    "has_apply_button": bool(extracted_email or target_url != href),
                    "first_published": None,
                    "discovered_at": now_iso,
                    "required_text": f"{title}. {q}",
                    "tasks": title,
                }
            time.sleep(0.35)
        except Exception:
            errors += 1

        try:
            rss_url = f"https://www.bing.com/search?q={urllib.parse.quote(q)}&format=rss&cc=EG"
            status, xml_raw = http_request(rss_url, timeout=15)
            root = ET.fromstring(xml_raw)
            for item in root.findall(".//item"):
                link = (item.findtext("link") or "").strip()
                raw_t = strip_tags(item.findtext("title") or "")
                desc = strip_tags(item.findtext("description") or "")
                combined = f"{raw_t}. {desc}"
                if not link.startswith("http") or link in found or not should_keep_role(raw_t, combined):
                    continue
                loc, mode = infer_location_and_mode(combined)
                target_url, extracted_email = extract_contact_or_apply_link(combined, link)
                found[link] = {
                    "company": "بوست توظيف (بحث مباشر)",
                    "title": raw_t[:125],
                    "location": loc,
                    "work_mode": mode,
                    "source_name": "بوستات التوظيف",
                    "source_category": "hiring_posts",
                    "url": target_url,
                    "post_url": link,
                    "apply_email": extracted_email,
                    "http_status": status,
                    "has_apply_button": bool(extracted_email or target_url != link),
                    "first_published": None,
                    "discovered_at": now_iso,
                    "required_text": f"{combined[:450]}. {q}",
                    "tasks": desc[:400] or raw_t,
                }
            time.sleep(0.3)
        except Exception:
            errors += 1

    for src_label, feed_url in COMMUNITY_RSS_FEEDS:
        try:
            status, xml_raw = http_request(feed_url, timeout=14)
            root = ET.fromstring(xml_raw)
            for item in root.findall(".//item"):
                link = (item.findtext("link") or "").strip()
                raw_t = strip_tags(item.findtext("title") or "")
                desc = strip_tags(item.findtext("description") or "")
                pub_raw = clean_field(item.findtext("pubDate"))
                combined = f"{raw_t}. {desc}"
                if not link.startswith("http") or link in found or not should_keep_role(raw_t, combined):
                    continue
                loc, mode = infer_location_and_mode(combined)
                target_url, extracted_email = extract_contact_or_apply_link(combined, link)
                found[link] = {
                    "company": src_label,
                    "title": raw_t[:125],
                    "location": loc,
                    "work_mode": mode,
                    "source_name": "بوستات التوظيف",
                    "source_category": "hiring_posts",
                    "url": target_url,
                    "post_url": link,
                    "apply_email": extracted_email,
                    "http_status": status,
                    "has_apply_button": bool(extracted_email or target_url != link),
                    "first_published": pub_raw,
                    "discovered_at": now_iso,
                    "required_text": combined[:450],
                    "tasks": desc[:400] or raw_t,
                }
            time.sleep(0.25)
        except Exception:
            errors += 1

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
                if not title or not should_keep_role(title, company):
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
                if not should_keep_role(title, f"{cat} {desc}"):
                    continue
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
    hp_items, hp_status = scrape_hiring_posts(now_iso)
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
