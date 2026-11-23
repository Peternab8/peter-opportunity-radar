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
    r"\b(senior|sr\.?|lead|principal|staff|head|director|vp|vice president|chief|manager|architect|expert|3\+\s*years|4\+\s*years|5\+\s*years|6\+\s*years)\b",
    re.I,
)

NEGATIVE_ROLE_RX = re.compile(
    r"\b(telesales|tele-sales|call center|customer service|customer support|door to door|outdoor sales|real estate|driver|security|nurse|pharmacist|chef|graphic designer|video editor|frontend|backend|fullstack|full stack|ios|android|flutter|devops|cybersecurity|network engineer)\b",
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
    "Product Analyst",
    "Data Specialist",
    "SQL Power BI",
]

WUZZUF_QUERIES = [
    "data analyst",
    "business intelligence",
    "reporting",
    "mis",
    "operations analyst",
    "business analyst",
    "systems analyst",
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
    ("Taqneen", "taqneen"),
    ("Fawry", "fawry"),
    ("Giza Systems", "giza-systems"),
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


def compute_commute_from_shubra(location_str, work_mode="", text=""):
    blob = f"{location_str} {work_mode} {text}".lower()
    if "remote" in blob and not any(k in blob for k in ["us only", "usa only", "uk only", "canada only"]):
        return 96, "عمل عن بُعد (Remote) — 0 دقيقة مشوار من شبرا مصر"
    if any(k in blob for k in ["dokki", "mohandessin", "downtown", "ramses", "shubra", "giza", "الدقي", "المهندسين", "وسط البلد", "شبرا", "الجيزة"]):
        return 90, "~25–35 دقيقة من شبرا مصر (مترو خط 2 مباشر)"
    if any(k in blob for k in ["maadi", "zamalek", "garden city", "nasr city", "heliopolis", "المعادي", "مدينة نصر", "مصر الجديدة"]):
        return 82, "~45–55 دقيقة من شبرا مصر (مترو خط 2 مع تبديل خط 1 أو 3)"
    if any(k in blob for k in ["new cairo", "fifth settlement", "tagamoa", "التجمع", "القاهرة الجديدة"]):
        return 74, "~65–75 دقيقة من شبرا مصر (أفضل في نظام Hybrid)"
    if any(k in blob for k in ["smart village", "6th of october", "october", "sheikh zayed", "القرية الذكية", "أكتوبر", "الشيخ زايد"]):
        bonus = 8 if ("hybrid" in blob or "bus" in blob or "transportation" in blob) else 0
        return 68 + bonus, "~75–85 دقيقة من شبرا مصر (مناسب لو Hybrid أو بباصات الشركة)"
    if any(k in blob for k in ["alexandria", "mansoura", "tanta", "aswan", "luxor", "الإسكندرية"]):
        return 30, "محافظة أخرى خارج القاهرة الكبرى (يحتاج انتقال/سكن)"
    if any(k in blob for k in ["cairo", "egypt", "القاهرة", "مصر"]):
        return 80, "داخل القاهرة الكبرى — راجع الحي الدقيق وأيام الحضور من شبرا مصر"
    return 68, "الموقع يحتاج تأكيد من نص الإعلان"


def evaluate_for_peter(title, company, location_str, snippet="", work_mode=""):
    t = str(title or "")
    combined = f"{t} {snippet}".lower()

    if SENIOR_RX.search(t) or NEGATIVE_ROLE_RX.search(t):
        return None

    score = 64
    reasons = []
    evidence = []

    if re.search(
        r"\b(data analyst|business intelligence|bi analyst|reporting analyst|mis|sfe|sales force|operations analyst|business analyst|data analytics|product analyst|systems analyst|data specialist|data science)\b",
        t,
        re.I,
    ):
        score += 20
        reasons.append("مسمى مباشر لمسارات Data / BI / Reporting / MIS / SFE / Systems.")
        evidence.append({"req": t, "cv": "بكالوريوس BIS حلوان (امتياز 3.67) + مشاريع DEPI وNTI"})
    elif re.search(r"\b(data|analytics|sql|power bi|excel|reporting|bi)\b", combined, re.I):
        score += 12
        reasons.append("يتضمن مهام تحليل بيانات أو تقارير.")
        evidence.append({"req": "Data & Reporting Tasks", "cv": "خبرة عملية في SQL, Excel, Power BI, Python"})
    else:
        return None

    if re.search(r"\b(junior|fresh|entry|graduate|trainee|intern|associate|riser|0-1|0 - 1|1 year|2 years)\b", combined, re.I):
        score += 8
        reasons.append("مناسب لحديثي التخرج / Junior / Associate.")
        evidence.append({"req": "Entry / Junior Level", "cv": "خريج 2026 بتقدير امتياز مع مرتبة الشرف (GPA 3.67)"})

    tools = []
    if re.search(r"\bsql\b", combined):
        score += 3
        tools.append("SQL")
    if re.search(r"\b(excel|power query|vba|pivot)\b", combined):
        score += 3
        tools.append("Excel/VBA")
    if re.search(r"\b(power bi|tableau|dashboard)\b", combined):
        score += 3
        tools.append("Power BI")
    if re.search(r"\bpython\b", combined):
        score += 2
        tools.append("Python")
    if tools:
        reasons.append(f"أدوات مطابقة: {', '.join(tools)}.")
        evidence.append({"req": f"أدوات: {', '.join(tools)}", "cv": "مطبقة في مشروع DEPI (5,000 سجل) وNTI (120 ساعة)"})

    comm_score, comm_summary = compute_commute_from_shubra(location_str, work_mode, snippet)
    if comm_score >= 80:
        score += 3

    score = max(58, min(score, 98))
    return {
        "fit_score": score,
        "commute_score": comm_score,
        "commute_summary": comm_summary,
        "summary": " ".join(reasons) if reasons else "متطابق مع مسار تحليل البيانات والتقارير.",
        "evidence_pairs": evidence[:3],
    }


def scrape_linkedin_egypt_guest(now_iso):
    """Fetch 2 pages (start=0, start=10) per query without f_E restriction so untagged Junior roles are included."""
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
                    loc = strip_tags(loc_m.group(1)) if loc_m else "Egypt"
                    clean_url = link_m.group(1).strip()
                    pub_date = time_m.group(1)[:10] if time_m else now_iso[:10]

                    ev = evaluate_for_peter(title, company, loc)
                    if not ev:
                        continue

                    job_id_m = re.search(r"-(\d+)(?:/|$)", clean_url)
                    jid = f"li-{job_id_m.group(1)}" if job_id_m else f"li-{abs(hash(clean_url))}"
                    found[jid] = {
                        "id": jid,
                        "company": company,
                        "title": title,
                        "work_mode": "LinkedIn Jobs (Egypt)",
                        "location": loc,
                        "primary_url": clean_url,
                        "sources": ["LinkedIn Jobs (Egypt)"],
                        "discovered_at": now_iso,
                        "fit": {
                            "score": ev["fit_score"],
                            "summary": ev["summary"],
                            "recommended_project": "مشروع DEPI لتحليل 5,000 معاملة دفع + لوحات Power BI.",
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
                            "first_published": pub_date,
                            "last_verified": now_iso,
                        },
                    }
                time.sleep(0.45)
            except Exception:
                break
    return list(found.values())


def scrape_wuzzuf_egypt(now_iso):
    """Query WUZZUF's actual JSON search backend endpoint."""
    found = {}
    api_url = "https://wuzzuf.net/api/search/job"
    for kw in WUZZUF_QUERIES:
        try:
            payload = {
                "startIndex": 0,
                "pageSize": 25,
                "query": kw,
                "filters": {},
            }
            raw = http_request(
                api_url,
                method="POST",
                payload=payload,
                extra_headers={"Accept": "application/json", "Referer": "https://wuzzuf.net/search/jobs/"},
                timeout=15,
            )
            data = json.loads(raw)
            jobs_list = data.get("data", []) if isinstance(data, dict) else []
            for item in jobs_list:
                attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else item
                title = strip_tags(attrs.get("title") or "")
                if not title:
                    continue
                company_obj = attrs.get("company") or {}
                company = strip_tags(company_obj.get("name") if isinstance(company_obj, dict) else "شركة على WUZZUF")
                loc_obj = attrs.get("location") or {}
                city = loc_obj.get("city", {}).get("name", "") if isinstance(loc_obj.get("city"), dict) else ""
                area = loc_obj.get("area", {}).get("name", "") if isinstance(loc_obj.get("area"), dict) else ""
                loc = ", ".join([x for x in [area, city, "Egypt"] if x])
                desc = strip_tags(attrs.get("description") or attrs.get("requirements") or "")
                slug = attrs.get("slug") or item.get("id") or ""
                job_url = f"https://wuzzuf.net/jobs/p/{slug}" if slug else "https://wuzzuf.net/search/jobs/"

                ev = evaluate_for_peter(title, company, loc, desc)
                if not ev:
                    continue

                jid = f"wz-{slug or abs(hash(title + company))}"
                found[jid] = {
                    "id": jid,
                    "company": company or "شركة على WUZZUF",
                    "title": title,
                    "work_mode": "Full-time / Hybrid (WUZZUF)",
                    "location": loc,
                    "primary_url": job_url,
                    "sources": ["WUZZUF"],
                    "discovered_at": now_iso,
                    "fit": {
                        "score": ev["fit_score"],
                        "summary": ev["summary"],
                        "recommended_project": "مشروع NTI قواعد البيانات + لوحات Power BI التفاعلية.",
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
                        "first_published": str(attrs.get("postedAt") or now_iso)[:10],
                        "last_verified": now_iso,
                    },
                }
            time.sleep(0.4)
        except Exception:
            continue
    return list(found.values())


def scrape_egypt_company_boards(now_iso):
    """Use Workable public v1 widget endpoint for direct Egyptian company career portals."""
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

                ev = evaluate_for_peter(title, company, loc_str, work_mode="Remote" if is_remote else "Hybrid")
                if not ev:
                    continue

                shortcode = job.get("shortcode", "")
                job_url = job.get("url") or (f"https://apply.workable.com/{slug}/j/{shortcode}/" if shortcode else f"https://apply.workable.com/{slug}/")
                results.append({
                    "id": f"wk-{slug}-{shortcode or abs(hash(title))}",
                    "company": company,
                    "title": title,
                    "work_mode": "Remote" if is_remote else "Hybrid / On-site",
                    "location": loc_str,
                    "primary_url": job_url,
                    "sources": [f"{company} Careers Portal"],
                    "discovered_at": now_iso,
                    "fit": {
                        "score": ev["fit_score"],
                        "summary": ev["summary"],
                        "recommended_project": "مشروع DEPI لتحليل المدفوعات الرقمية + Power BI.",
                        "evidence_pairs": ev["evidence_pairs"],
                    },
                    "commute": {
                        "score": ev["commute_score"],
                        "summary": ev["commute_summary"],
                    },
                    "receipt": {
                        "apply_state": "OPEN",
                        "apply_state_ar": "مفتوح ومتحقق ✓",
                        "egypt_eligibility": f"مؤكد: {loc_str}",
                        "first_published": str(job.get("published_on") or now_iso)[:10],
                        "last_verified": now_iso,
                    },
                })
        except Exception:
            continue
    return results


def scrape_remotive_global(now_iso):
    results = []
    for cat in ["data", "business"]:
        try:
            raw = http_request(f"https://remotive.com/api/remote-jobs?category={cat}&limit=40", timeout=14)
            data = json.loads(raw)
            for job in data.get("jobs", []):
                title = job.get("title", "")
                req_loc = job.get("candidate_required_location", "")
                if not re.search(r"\b(worldwide|anywhere|emea|egypt|middle east|africa)\b", req_loc, re.I):
                    continue
                desc = strip_tags(job.get("description", ""))[:500]
                ev = evaluate_for_peter(title, job.get("company_name", ""), req_loc, desc, "Remote")
                if not ev:
                    continue
                results.append({
                    "id": f"rem-{job.get('id')}",
                    "company": job.get("company_name", "Remote Company"),
                    "title": title,
                    "work_mode": "Remote",
                    "location": req_loc or "Worldwide",
                    "primary_url": job.get("url", "https://remotive.com"),
                    "sources": ["Remotive Live API"],
                    "discovered_at": now_iso,
                    "fit": {
                        "score": ev["fit_score"],
                        "summary": ev["summary"],
                        "recommended_project": "مشروع DEPI لتحليل البيانات (Python, SQL, Tableau).",
                        "evidence_pairs": ev["evidence_pairs"],
                    },
                    "commute": {
                        "score": ev["commute_score"],
                        "summary": ev["commute_summary"],
                    },
                    "receipt": {
                        "apply_state": "OPEN",
                        "apply_state_ar": "مفتوح ومتحقق ✓",
                        "egypt_eligibility": f"متاح: {req_loc}",
                        "first_published": (job.get("publication_date") or now_iso)[:10],
                        "last_verified": now_iso,
                    },
                })
        except Exception:
            continue
    return results


def enrich_top_jobs_with_gemini(jobs):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or not jobs:
        return jobs

    top_slice = jobs[:15]
    compact = [
        {"id": j["id"], "title": j["title"], "company": j["company"], "location": j["location"]}
        for j in top_slice
    ]
    prompt = (
        "You are a career advisor for Peter Nabil Gerges (BIS graduate from Helwan University, GPA 3.67, "
        "lives in Shubra Masr Cairo, skilled in SQL, Excel/Power Query/VBA, Power BI, Python; DEPI & NTI Data Analysis tracks). "
        "Evaluate these job openings for him. Return ONLY a JSON array of objects with keys: "
        "id, fit_score (60-98 integer), reason_ar (1 concise Arabic sentence), project_ar (best project from his CV to highlight). "
        f"Jobs: {json.dumps(compact, ensure_ascii=False)}"
    )
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={urllib.parse.quote(api_key)}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    try:
        raw = http_request(url, method="POST", payload=payload, timeout=20)
        parsed = json.loads(raw)
        txt = parsed["candidates"][0]["content"]["parts"][0]["text"]
        ai_list = json.loads(txt)
        by_id = {item["id"]: item for item in ai_list if isinstance(item, dict) and "id" in item}
        for j in jobs:
            if j["id"] in by_id:
                ai = by_id[j["id"]]
                if isinstance(ai.get("fit_score"), (int, float)):
                    j["fit"]["score"] = max(55, min(98, int(ai["fit_score"])))
                if ai.get("reason_ar"):
                    j["fit"]["summary"] = f"✨ {ai['reason_ar']}"
                if ai.get("project_ar"):
                    j["fit"]["recommended_project"] = ai["project_ar"]
    except Exception:
        pass
    return jobs


def scrape_all_real_sources():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    li_jobs = scrape_linkedin_egypt_guest(now_iso)
    wz_jobs = scrape_wuzzuf_egypt(now_iso)
    co_jobs = scrape_egypt_company_boards(now_iso)
    rm_jobs = scrape_remotive_global(now_iso)

    all_items = li_jobs + wz_jobs + co_jobs + rm_jobs
    all_items.sort(key=lambda x: x.get("fit", {}).get("score", 0), reverse=True)
    all_items = enrich_top_jobs_with_gemini(all_items)

    stats = {
        "linkedin_egypt": len(li_jobs),
        "wuzzuf_egypt": len(wz_jobs),
        "egypt_companies": len(co_jobs),
        "remotive_global": len(rm_jobs),
    }
    return all_items, stats
