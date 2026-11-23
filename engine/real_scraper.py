import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

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
    r"\b(telesales|tele-sales|call center|customer service|customer support|door to door|outdoor sales|real estate|driver|security|nurse|pharmacist|chef|graphic designer|video editor|frontend|backend|fullstack|ios|android|flutter|devops)\b",
    re.I,
)

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

# Free unlimited web search queries via Bing RSS & DuckDuckGo HTML (bypasses WUZZUF/LinkedIn firewalls)
WEB_XRAY_QUERIES = [
    ("WUZZUF", 'site:wuzzuf.net/jobs/p ("Data Analyst" OR "Business Intelligence" OR "Reporting" OR "MIS" OR "Operations Analyst")'),
    ("WUZZUF", 'site:wuzzuf.net/jobs/p ("Business Analyst" OR "Systems Analyst" OR "Data" OR "SFE")'),
    ("LinkedIn HR Post", 'site:linkedin.com/posts ("Data Analyst" OR "BI Analyst" OR "MIS" OR "SFE" OR "Reporting") ("Cairo" OR "Egypt")'),
    ("Indeed Egypt", 'site:eg.indeed.com ("Data Analyst" OR "BI" OR "Reporting" OR "Operations Analyst") Cairo'),
    ("Egypt Company Portal", '(site:apply.workable.com OR site:jobs.lever.co OR site:boards.greenhouse.io OR site:jobs.smartrecruiters.com) ("Data Analyst" OR "BI" OR "Operations Analyst" OR "Business Analyst") ("Cairo" OR "Egypt")'),
]


def http_request(url, method="GET", payload=None, extra_headers=None, timeout=18):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = None
    if payload is not None:
        if isinstance(payload, bytes):
            data = payload
        else:
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


def parse_company_and_title(raw_title, fallback_company):
    clean = strip_tags(raw_title)
    clean = re.sub(r"\s*[-|]\s*(WUZZUF|LinkedIn|Indeed|Bayt|Glassdoor).*$", "", clean, flags=re.I).strip()
    if " at " in clean:
        parts = clean.split(" at ", 1)
        return parts[0].strip(), parts[1].strip()
    if " - " in clean:
        parts = clean.split(" - ", 1)
        if len(parts[1]) < 45:
            return parts[0].strip(), parts[1].strip()
    return clean, fallback_company


def scrape_search_engines_xray(now_iso):
    """Uses Bing Search RSS and DuckDuckGo HTML to extract indexed WUZZUF, LinkedIn Posts & Company Portals."""
    found = {}

    # 1. Bing Search RSS (Native XML feed, $0, zero API keys)
    for source_label, query in WEB_XRAY_QUERIES:
        rss_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&format=rss&cc=EG"
        try:
            xml_text = http_request(rss_url, timeout=16)
            root = ET.fromstring(xml_text)
            for item in root.findall(".//item"):
                raw_t = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc = strip_tags(item.findtext("description") or "")
                if not raw_t or not link.startswith("http"):
                    continue
                title, company = parse_company_and_title(raw_t, source_label)
                if not is_relevant_entry_role(title, desc):
                    continue
                found[link] = {
                    "company": company,
                    "title": title,
                    "location": "Cairo, Egypt",
                    "work_mode": "Hybrid",
                    "source_name": source_label,
                    "url": link,
                    "first_published": now_iso[:10],
                    "discovered_at": now_iso,
                    "required_text": f"{title} {desc[:350]}",
                    "tasks": desc[:350] or title,
                }
            time.sleep(0.4)
        except Exception:
            continue

    # 2. DuckDuckGo HTML fallback for WUZZUF & LinkedIn Posts
    ddg_queries = [
        ("WUZZUF", 'site:wuzzuf.net/jobs/p "data analyst" OR "bi analyst" OR "reporting"'),
        ("LinkedIn HR Post", 'site:linkedin.com/posts "data analyst" OR "mis" OR "sfe" egypt'),
    ]
    for source_label, query in ddg_queries:
        try:
            ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            body = http_request(ddg_url, timeout=16)
            blocks = re.findall(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', body, flags=re.S)
            for href, raw_t in blocks:
                if "uddg=" in href:
                    m = re.search(r"uddg=([^&]+)", href)
                    if m:
                        href = urllib.parse.unquote(m.group(1))
                if not href.startswith("http") or href in found:
                    continue
                title, company = parse_company_and_title(raw_t, source_label)
                if not is_relevant_entry_role(title):
                    continue
                found[href] = {
                    "company": company,
                    "title": title,
                    "location": "Cairo, Egypt",
                    "work_mode": "Hybrid",
                    "source_name": source_label,
                    "url": href,
                    "first_published": now_iso[:10],
                    "discovered_at": now_iso,
                    "required_text": f"{title} SQL Power BI Excel",
                    "tasks": title,
                }
            time.sleep(0.5)
        except Exception:
            continue

    return list(found.values())


def scrape_linkedin_egypt_guest(now_iso):
    """Fetches 3 pages (0, 10, 20) across 14 keywords from LinkedIn Egypt public job index."""
    found = {}
    for kw in LINKEDIN_QUERIES:
        encoded_kw = urllib.parse.quote(kw)
        for start in [0, 10, 20]:
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
    xray_jobs = scrape_search_engines_xray(now_iso)
    li_jobs = scrape_linkedin_egypt_guest(now_iso)
    rm_jobs = scrape_remotive_global(now_iso)

    raw_items = xray_jobs + li_jobs + rm_jobs
    wuzzuf_cnt = sum(1 for j in xray_jobs if "wuzzuf" in j.get("source_name", "").lower())
    other_egypt_cnt = len(xray_jobs) - wuzzuf_cnt

    stats = {
        "ai_google_search": len(xray_jobs),
        "gemini_status": f"محرك X-Ray المجاني شغّال ✓ ({len(xray_jobs)} نتيجة)",
        "linkedin_egypt": len(li_jobs),
        "wuzzuf_egypt": wuzzuf_cnt,
        "egypt_companies": other_egypt_cnt,
        "remotive_global": len(rm_jobs),
    }
    return raw_items, stats
