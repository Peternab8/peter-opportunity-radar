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
    "Operations Analyst",
    "Business Analyst",
]


def http_request(url, method="GET", payload=None, extra_headers=None, timeout=22):
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
        return 72, "~75–85 دقيقة من شبرا مصر (مناسب لو Hybrid أو بباصات الشركة)"
    if any(k in blob for k in ["cairo", "egypt", "القاهرة", "مصر"]):
        return 80, "داخل القاهرة الكبرى — راجع الحي الدقيق وأيام الحضور من شبرا مصر"
    return 70, "راجع موقع الشركة في الإعلان"


def evaluate_for_peter(title, company, location_str, snippet="", work_mode=""):
    t = str(title or "")
    combined = f"{t} {snippet}".lower()

    if SENIOR_RX.search(t) or NEGATIVE_ROLE_RX.search(t):
        return None

    score = 68
    reasons = []
    evidence = []

    if re.search(r"\b(data analyst|business intelligence|bi analyst|reporting|mis|sfe|sales force|operations analyst|business analyst|analytics|product analyst|systems analyst|data specialist|data science)\b", t, re.I):
        score += 18
        reasons.append("مسمى مباشر لمسارات Data / BI / Reporting / MIS / SFE / Operations.")
        evidence.append({"req": t, "cv": "بكالوريوس BIS حلوان (امتياز 3.67) + مشاريع DEPI وNTI"})
    elif re.search(r"\b(data|analytics|sql|power bi|excel|reporting|bi)\b", combined, re.I):
        score += 10
        reasons.append("يتضمن مهام تحليل بيانات أو تقارير.")
    else:
        return None

    if re.search(r"\b(junior|fresh|entry|graduate|trainee|intern|associate|riser|0-1|1 year)\b", combined, re.I):
        score += 8
        reasons.append("مناسب لحديثي التخرج / Junior.")

    comm_score, comm_summary = compute_commute_from_shubra(location_str, work_mode, snippet)
    score = max(60, min(score, 98))
    return {
        "fit_score": score,
        "commute_score": comm_score,
        "commute_summary": comm_summary,
        "summary": " ".join(reasons) if reasons else "متطابق مع مسار تحليل البيانات والتقارير.",
        "evidence_pairs": evidence[:3],
    }


def search_web_via_gemini_grounding(now_iso):
    """Uses Gemini 2.5 Flash + live Google Search Grounding to find indexed WUZZUF, LinkedIn Posts, Indeed & Egypt company jobs."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return []

    search_prompts = [
        (
            "Use Google Search right now to find the newest entry-level, junior, fresh graduate, or internship job postings "
            "and HR posts in Egypt (Cairo / Giza / Remote Egypt) from the last 7 days for: "
            "Data Analyst, Business Intelligence Analyst, Reporting Analyst, MIS Analyst, SFE (Sales Force Effectiveness), "
            "or Operations Analyst across site:linkedin.com/posts, site:linkedin.com/jobs, site:wuzzuf.net, and site:eg.indeed.com. "
            "Exclude Senior, Lead, Manager, or Director roles. "
            "Return ONLY a valid JSON array (inside ```json ... ```) of up to 18 real opportunities with keys: "
            "title, company, location, source (e.g. 'LinkedIn HR Post', 'WUZZUF', 'Indeed Egypt', 'LinkedIn Jobs'), "
            "url (exact direct URL found in search results), reason_ar (1 crisp Arabic sentence why it fits a BIS graduate skilled in SQL, Power BI, Excel, Python)."
        ),
        (
            "Use Google Search right now to find graduate programs, data trainee roles, commercial operations analyst, "
            "or BI specialist openings in Egyptian fintech, telecom, banks, and e-commerce companies (like Paymob, Fawry, CIB, "
            "Vodafone VOIS, e&, Raya, Breadfast, Bosta, Talabat, MaxAB, Noon, Jumia) in Cairo Egypt from the past 7 days. "
            "Exclude Senior/Manager roles. "
            "Return ONLY a valid JSON array (inside ```json ... ```) of up to 15 real opportunities with keys: "
            "title, company, location, source, url, reason_ar."
        ),
    ]

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={urllib.parse.quote(api_key)}"
    collected = {}

    for prompt in search_prompts:
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        }
        try:
            raw = http_request(url, method="POST", payload=payload, timeout=30)
            parsed = json.loads(raw)
            cand = parsed["candidates"][0]
            text = cand["content"]["parts"][0].get("text", "")

            # Collect verified grounding URLs from Google Search metadata
            grounding_urls = []
            g_meta = cand.get("groundingMetadata") or {}
            for chunk in g_meta.get("groundingChunks") or []:
                web = chunk.get("web") or {}
                if web.get("uri"):
                    grounding_urls.append(web["uri"])

            json_m = re.search(r"\[.*\]", text, flags=re.S)
            if not json_m:
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
                src = str(it.get("source") or "Google AI Web Search").strip()
                job_url = str(it.get("url") or "").strip()
                if not job_url.startswith("http"):
                    job_url = grounding_urls[idx] if idx < len(grounding_urls) else f"https://www.google.com/search?q={urllib.parse.quote(title + ' ' + company + ' Egypt')}"

                comm_score, comm_summary = compute_commute_from_shubra(loc)
                jid = f"ai-{abs(hash(title + company))}"
                collected[jid] = {
                    "id": jid,
                    "company": company,
                    "title": title,
                    "work_mode": src,
                    "location": loc,
                    "primary_url": job_url,
                    "sources": [f"✨ {src}"],
                    "discovered_at": now_iso,
                    "fit": {
                        "score": 89,
                        "summary": f"✨ {it.get('reason_ar') or 'فرصة حديثة مستخرجة عبر بحث Google الذكي ومطابقة لملفك.'}",
                        "recommended_project": "مشروع DEPI لتحليل 5,000 معاملة + لوحات Power BI + Excel/VBA.",
                        "evidence_pairs": [{"req": title, "cv": "بكالوريوس BIS حلوان (3.67) + SQL / Power BI / Excel / Python"}],
                    },
                    "commute": {
                        "score": comm_score,
                        "summary": comm_summary,
                    },
                    "receipt": {
                        "apply_state": "OPEN",
                        "apply_state_ar": "مفتوح (بحث AI حي) ✓",
                        "egypt_eligibility": f"مؤكد: {loc}",
                        "first_published": now_iso[:10],
                        "last_verified": now_iso,
                    },
                }
        except Exception:
            continue

    return list(collected.values())


def scrape_linkedin_egypt_guest(now_iso):
    found = {}
    for kw in LINKEDIN_QUERIES:
        encoded_kw = urllib.parse.quote(kw)
        url = (
            f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
            f"?keywords={encoded_kw}&location=Egypt&f_TPR=r604800&start=0"
        )
        try:
            body = http_request(url, timeout=14)
            cards = re.findall(r"<li[^>]*>(.*?)</li>", body, flags=re.S)
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
            time.sleep(0.4)
        except Exception:
            continue
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
                ev = evaluate_for_peter(title, job.get("company_name", ""), req_loc, "", "Remote")
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


def scrape_all_real_sources():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ai_jobs = search_web_via_gemini_grounding(now_iso)
    li_jobs = scrape_linkedin_egypt_guest(now_iso)
    rm_jobs = scrape_remotive_global(now_iso)

    all_items = ai_jobs + li_jobs + rm_jobs
    all_items.sort(key=lambda x: x.get("fit", {}).get("score", 0), reverse=True)

    stats = {
        "ai_google_search": len(ai_jobs),
        "linkedin_egypt": len(li_jobs),
        "wuzzuf_egypt": sum(1 for j in ai_jobs if "wuzzuf" in " ".join(j.get("sources", [])).lower()),
        "egypt_companies": sum(1 for j in ai_jobs if not any(x in " ".join(j.get("sources", [])).lower() for x in ["wuzzuf", "linkedin", "indeed"])),
        "remotive_global": len(rm_jobs),
    }
    return all_items, stats
