import os
import re
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import List, Dict, Optional

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"

# Expanded Keyword Matrix (Arabic + English + Recruiter Slang)
KEYWORD_CLUSTERS = {
    "bi_data": [
        "Data Analyst", "Junior Data Analyst", "BI Analyst", "Junior BI",
        "Business Intelligence", "Power BI", "SQL Analyst", "Data Analytics"
    ],
    "reporting_mis": [
        "Reporting Analyst", "MIS Analyst", "MIS Specialist", "Performance Reporting",
        "Management Information Systems", "KPI Analyst", "Dashboard"
    ],
    "commercial_sfe": [
        "SFE", "Sales Force Effectiveness", "Sales Operations", "Commercial Excellence",
        "Sales Support Analyst", "Commercial Analyst", "Revenue Operations"
    ],
    "ba_ops_intern": [
        "Business Analyst", "Operations Analyst", "System Analyst", "Graduate Program",
        "Data Internship", "BI Internship", "Fresh Graduate", "تحليل بيانات", "مطلوب فريش"
    ]
}

# 20+ Top Egyptian & Regional Companies on Workable / Lever / Greenhouse Public JSON APIs
ATS_BOARDS = [
    {"company": "Paymob", "ats": "workable", "slug": "paymob"},
    {"company": "Breadfast", "ats": "workable", "slug": "breadfast"},
    {"company": "Thndr", "ats": "workable", "slug": "thndr"},
    {"company": "MaxAB", "ats": "workable", "slug": "maxab"},
    {"company": "Khazna", "ats": "workable", "slug": "khazna"},
    {"company": "Bosta", "ats": "workable", "slug": "bosta"},
    {"company": "MoneyFellows", "ats": "workable", "slug": "moneyfellows"},
    {"company": "Vezeeta", "ats": "workable", "slug": "vezeeta"},
    {"company": "valU", "ats": "workable", "slug": "valu"},
    {"company": "MNT-Halan", "ats": "workable", "slug": "mnt-halan"},
    {"company": "Rabbit Mart", "ats": "workable", "slug": "rabbit"},
    {"company": "Trella", "ats": "workable", "slug": "trella"},
    {"company": "Yodawy", "ats": "workable", "slug": "yodawy"},
    {"company": "Homzmart", "ats": "workable", "slug": "homzmart"},
    {"company": "Cartona", "ats": "workable", "slug": "cartona"},
    {"company": "Instabug", "ats": "lever", "slug": "instabug"},
    {"company": "Swvl", "ats": "lever", "slug": "swvl"},
    {"company": "Talabat", "ats": "greenhouse", "slug": "talabat"}
]

TARGET_TITLE_REGEX = re.compile(
    r"(data|bi|business intelligence|reporting|mis|sfe|sales ops|sales operations|commercial|business analyst|operations analyst|system analyst|analytics|kpi|power bi|sql|intern|graduate|trainee)",
    re.IGNORECASE
)


def http_get(url: str, timeout: int = 12) -> Optional[str]:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/html, application/xml;q=0.9, */*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,ar;q=0.8"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None
    return None


def scrape_ats_company_boards() -> List[Dict]:
    """Queries public JSON endpoints of Workable, Lever, and Greenhouse for Egyptian companies."""
    found = []
    for b in ATS_BOARDS:
        ats = b["ats"]
        slug = b["slug"]
        company = b["company"]
        if ats == "workable":
            raw = http_get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
            if raw:
                try:
                    data = json.loads(raw)
                    for j in data.get("jobs", []):
                        title = j.get("title", "")
                        country = (j.get("country") or "").lower()
                        city = j.get("city") or ""
                        if TARGET_TITLE_REGEX.search(title) and ("egypt" in country or "cairo" in city.lower() or not country):
                            found.append({
                                "source_channel": "ats_career_pages",
                                "source_name": f"{company} Careers (Workable)",
                                "company": company,
                                "title": title,
                                "req_id": j.get("shortcode"),
                                "url": j.get("url") or f"https://apply.workable.com/{slug}/j/{j.get('shortcode')}/",
                                "posted_at": j.get("published_on"),
                                "location": f"{city}, Egypt" if city else "Cairo, Egypt",
                                "work_mode": "Remote" if j.get("telecommuting") else "On-site / Hybrid",
                                "tasks": f"{title} {j.get('department', '')}",
                                "http_status": 200
                            })
                except Exception:
                    pass
        elif ats == "lever":
            raw = http_get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
            if raw:
                try:
                    for j in json.loads(raw):
                        title = j.get("text", "")
                        loc = (j.get("categories") or {}).get("location", "")
                        if TARGET_TITLE_REGEX.search(title) and ("egypt" in loc.lower() or "cairo" in loc.lower() or "remote" in loc.lower()):
                            found.append({
                                "source_channel": "ats_career_pages",
                                "source_name": f"{company} Careers (Lever)",
                                "company": company,
                                "title": title,
                                "req_id": j.get("id"),
                                "url": j.get("hostedUrl"),
                                "location": loc or "Cairo, Egypt",
                                "tasks": j.get("descriptionPlain", "")[:1000],
                                "http_status": 200
                            })
                except Exception:
                    pass
        elif ats == "greenhouse":
            raw = http_get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
            if raw:
                try:
                    data = json.loads(raw)
                    for j in data.get("jobs", []):
                        title = j.get("title", "")
                        loc = (j.get("location") or {}).get("name", "")
                        if TARGET_TITLE_REGEX.search(title) and ("egypt" in loc.lower() or "cairo" in loc.lower()):
                            found.append({
                                "source_channel": "ats_career_pages",
                                "source_name": f"{company} Careers (Greenhouse)",
                                "company": company,
                                "title": title,
                                "req_id": str(j.get("id")),
                                "url": j.get("absolute_url"),
                                "posted_at": j.get("updated_at"),
                                "location": loc,
                                "tasks": title,
                                "http_status": 200
                            })
                except Exception:
                    pass
        time.sleep(0.15)
    return found


def scrape_linkedin_guest_jobs(keywords: List[str], max_pages: int = 2) -> List[Dict]:
    """Scrapes LinkedIn public guest search HTML for Egypt Entry-Level & Internships (past 24h)."""
    results = []
    for kw in keywords:
        for page in range(max_pages):
            start = page * 25
            q = urllib.parse.quote(kw)
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={q}&location=Egypt&geoId=106155005&f_E=1%2C2&f_TPR=r86400&start={start}"
            html = http_get(url)
            if not html:
                continue
            cards = re.findall(r'<li[^>]*>(.*?)</li>', html, flags=re.DOTALL)
            for c in cards:
                link_m = re.search(r'href="(https://www\.linkedin\.com/jobs/view/[^"?]+)', c)
                title_m = re.search(r'class="base-search-card__title"[^>]*>(.*?)</', c, flags=re.DOTALL)
                comp_m = re.search(r'class="base-search-card__subtitle"[^>]*>.*?<a[^>]*>(.*?)</a>', c, flags=re.DOTALL)
                loc_m = re.search(r'class="job-search-card__location"[^>]*>(.*?)</', c, flags=re.DOTALL)
                time_m = re.search(r'datetime="([^"]+)"', c)
                if link_m and title_m:
                    results.append({
                        "source_channel": "linkedin_public_posts",
                        "source_name": "LinkedIn Public Jobs",
                        "company": re.sub(r"<[^>]+>", "", comp_m.group(1)).strip() if comp_m else "Unknown",
                        "title": re.sub(r"<[^>]+>", "", title_m.group(1)).strip(),
                        "url": link_m.group(1).strip(),
                        "location": re.sub(r"<[^>]+>", "", loc_m.group(1)).strip() if loc_m else "Egypt",
                        "posted_at": time_m.group(1) if time_m else None,
                        "tasks": kw,
                        "http_status": 200
                    })
            time.sleep(0.35)
    return results


def scrape_wuzzuf_public(keywords: List[str]) -> List[Dict]:
    """Scrapes WUZZUF public search listings for Entry-Level roles."""
    results = []
    for kw in keywords:
        q = urllib.parse.quote(kw)
        url = f"https://wuzzuf.net/search/jobs/?a=navbl&q={q}&filters%5Bcareer_level%5D%5B0%5D=entry_level"
        html = http_get(url)
        if not html:
            continue
        links = re.findall(r'href="(https://wuzzuf\.net/jobs/p/[^"]+)"[^>]*>(.*?)</a>', html, flags=re.DOTALL)
        for href, raw_title in links:
            clean_title = re.sub(r"<[^>]+>", "", raw_title).strip()
            if len(clean_title) >= 4:
                results.append({
                    "source_channel": "wuzzuf",
                    "source_name": "WUZZUF",
                    "company": "WUZZUF Employer",
                    "title": clean_title,
                    "url": href,
                    "location": "Cairo, Egypt",
                    "tasks": kw,
                    "http_status": 200
                })
        time.sleep(0.25)
    return results


def scrape_remote_global_apis() -> List[Dict]:
    """Scrapes Remotive & Himalayas public JSON APIs for Remote Data/BI roles open to Egypt."""
    results = []
    for api_url, src_label in [
        ("https://remotive.com/api/remote-jobs?category=data&limit=40", "Remotive Remote"),
        ("https://himalayas.app/jobs/api?limit=40", "Himalayas Remote")
    ]:
        raw = http_get(api_url)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            jobs = data.get("jobs", [])
            for j in jobs:
                title = j.get("title", "")
                if not TARGET_TITLE_REGEX.search(title):
                    continue
                loc = j.get("candidate_required_location") or ", ".join(j.get("locationRestrictions") or []) or "Worldwide"
                if any(k in loc.lower() for k in ["worldwide", "anywhere", "emea", "egypt", "africa", "middle east", "global"]):
                    results.append({
                        "source_channel": "bayt_gulftalent_naukri",
                        "source_name": src_label,
                        "company": j.get("company_name") or j.get("companyName") or "Remote Company",
                        "title": title,
                        "url": j.get("url") or j.get("applicationLink") or "",
                        "posted_at": j.get("publication_date") or j.get("pubDate"),
                        "tasks": re.sub(r"<[^>]+>", " ", j.get("description", ""))[:1200],
                        "location": loc,
                        "work_mode": "Remote",
                        "salary": j.get("salary") or None,
                        "http_status": 200
                    })
        except Exception:
            pass
    return results


def send_real_android_push_ntfy(topic: str, title: str, body: str, click_url: str, priority: str = "high") -> bool:
    """
    Sends a REAL native Android system notification with sound & vibration to Samsung Galaxy A71
    via ntfy.sh — works even when all browsers and apps are completely closed!
    """
    if not topic:
        return False
    try:
        req = urllib.request.Request(
            f"https://ntfy.sh/{urllib.parse.quote(topic)}",
            data=body.encode("utf-8"),
            method="POST",
            headers={
                "Title": title.encode("ascii", "ignore").decode("ascii") or "New Job Match - Peter Radar",
                "Priority": priority,
                "Tags": "briefcase,chart_with_upwards_trend",
                "Click": click_url,
                "Actions": f"view, Open Job, {click_url}"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 201)
    except Exception:
        return False


def run_full_hourly_scrape() -> List[Dict]:
    all_raw = []
    flat_kw = [kw for grp in KEYWORD_CLUSTERS.values() for kw in grp]
    all_raw.extend(scrape_ats_company_boards())
    all_raw.extend(scrape_linkedin_guest_jobs(flat_kw[:14], max_pages=2))
    all_raw.extend(scrape_wuzzuf_public(flat_kw[:10]))
    all_raw.extend(scrape_remote_global_apis())
    return all_raw
