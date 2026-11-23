import re
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple

PETER_CV_EVIDENCE = {
    "sql": {
        "label": "SQL & Relational Databases",
        "evidence": "مشروع NTI (تصميم قاعدة بيانات 6+ كيانات ERD) + تحليل بيانات الطلاب والدفع الرقمي بـ SQL Server/MySQL"
    },
    "power_bi": {
        "label": "Power BI & Dashboards",
        "evidence": "لوحة متابعة تفاعلية KPI Dashboard لمشروع تحليل أداء الطلاب (1,000+ سجل) وتدريب NTI (120 ساعة - 85%)"
    },
    "tableau": {
        "label": "Tableau Visualization",
        "evidence": "لوحة Tableau من 5+ رسوم بيانية لمشروع التخرج في مبادرة DEPI (تحليل 5,000 معاملة دفع رقمي)"
    },
    "excel_vba": {
        "label": "Advanced Excel, Power Query & VBA",
        "evidence": "بناء نظام حجز فعاليات كامل بـ Excel/VBA وأتمتة رسائل التأكيد وتشغيله فعليًا لـ 500–1,000 مشارك"
    },
    "python": {
        "label": "Python (Pandas / NumPy / EDA)",
        "evidence": "تنظيف وتحليل استكشافي (EDA) لـ 5,000 معاملة في DEPI و1,000 سجل طلاب في NTI"
    },
    "ba_sa": {
        "label": "Business & Systems Analysis (UML / SDLC)",
        "evidence": "قائد تحليل النظم والبيانات في مشروع التخرج BIS حلوان (امتياز A+) + منصة FeeLink"
    },
    "fresh_grad": {
        "label": "بكالوريوس BIS جامعة حلوان 2026 (امتياز مع مرتبة الشرف GPA 3.67)",
        "evidence": "خريج 2026 مع خبرة عمل حر (3+ مشاريع تحليل بيانات) وتدريبات CIB وبنك القاهرة والبنك المركزي"
    }
}

COMMUTE_ZONES = {
    "shubra masr": (15, 0, "داخل شبرا مصر — مشي أو مواصلة واحدة قصيرة"),
    "ramses": (18, 0, "مترو خط 2 مباشر من شبرا لمحطة الشهداء (رمسيس)"),
    "downtown": (22, 0, "مترو خط 2 مباشر لمحطة السادات / محمد نجيب"),
    "shubra el kheima": (20, 0, "مترو خط 2 مباشر"),
    "dokki": (30, 0, "مترو خط 2 مباشر لمحطة الدقي + 5 دقايق مشي"),
    "mohandessin": (38, 1, "مترو خط 2 للبحوث + ميكروباص قصير"),
    "giza": (38, 0, "مترو خط 2 مباشر لمحطة الجيزة"),
    "zamalek": (35, 1, "مترو الأوبرا أو مواصلة مباشرة من رمسيس"),
    "heliopolis": (45, 1, "مترو خط 2 للعتبة ثم تبديل خط 3 (الأهرام / هليوبوليس)"),
    "nasr city": (52, 1, "مترو خط 3 (الاستاد / أرض المعارض) أو أتوبيس من رمسيس"),
    "maadi": (55, 1, "مترو خط 2 للسادات ثم تبديل خط 1 (المعادي / ثكنات المعادي)"),
    "smart village": (80, 2, "مواصلة لرمسيس/عبدالمنعم رياض + ميكروباص القرية الذكية"),
    "6th of october": (85, 2, "مواصلة للجيزة/رمسيس + مواصلة 6 أكتوبر"),
    "new cairo": (78, 2, "مترو خط 3 لعدلي منصور/الاستاد + مواصلة التجمع"),
    "fifth settlement": (78, 2, "مترو خط 3 + مواصلة التجمع الخامس"),
    "sheikh zayed": (75, 2, "مواصلة من رمسيس أو الجيزة للشيخ زايد"),
    "new administrative capital": (105, 2, "مترو خط 3 لعدلي منصور + القطار الكهربائي LRT")
}


def normalize_str(s: str) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\u0600-\u06FF\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def has_word(text: str, word: str) -> bool:
    return bool(re.search(r"(?:^|\s)" + re.escape(word) + r"(?:$|\s)", text))


def compute_job_identity(company: str, title: str, req_id: Optional[str] = None, location: Optional[str] = None) -> Tuple[str, str]:
    """
    Returns (exact_id, loose_role_family_id).
    Two DIFFERENT roles at the SAME company get DIFFERENT exact_ids!
    Same role reposted across LinkedIn + WUZZUF gets the SAME exact_id.
    """
    co = normalize_str(company)
    noise = {"urgent", "hiring", "immediate", "fresh", "graduate", "junior", "for", "and", "مطلوب", "فورا", "حديثي", "التخرج"}
    core_tokens = sorted(set(t for t in normalize_str(title).split() if t not in noise))
    clean_title = " ".join(core_tokens)
    if req_id:
        exact_raw = f"{co}::req::{normalize_str(req_id)}"
    else:
        exact_raw = f"{co}::title::{clean_title}"
    exact_id = hashlib.sha256(exact_raw.encode("utf-8")).hexdigest()[:16]
    # Loose family ID (same company + overlapping first token) to warn about 'probable same role'
    primary_tok = core_tokens[0] if core_tokens else "role"
    loose_id = hashlib.sha256(f"{co}::family::{primary_tok}".encode("utf-8")).hexdigest()[:12]
    return exact_id, loose_id


def verify_receipt_and_status(item: Dict, check_time_iso: str) -> Dict:
    """Builds the auditable Verification Receipt for a job card."""
    body_lower = (item.get("page_body", "") + " " + item.get("description", "")).lower()
    http_status = item.get("http_status", 200)
    closed_phrases = [
        "no longer accepting applications", "this job is closed", "position has been filled",
        "expired", "تم إغلاق التقديم", "انتهى التقديم", "الوظيفة مغلقة"
    ]
    is_closed = http_status in (404, 410) or any(p in body_lower for p in closed_phrases)
    has_apply_cta = bool(item.get("resolved_apply_url") or item.get("apply_email") or item.get("has_apply_button", True))

    if is_closed:
        apply_state = "CLOSED"
        apply_state_ar = "مغلق / منتهي"
    elif has_apply_cta and item.get("url"):
        apply_state = "OPEN_VERIFIED"
        apply_state_ar = "مفتوح ومتحقق"
    else:
        apply_state = "NEEDS_VERIFICATION"
        apply_state_ar = "محتاج تحقق"

    # Egypt Remote Eligibility check
    work_mode = normalize_str(item.get("work_mode", ""))
    eligible_regions = normalize_str(item.get("eligible_regions", ""))
    loc_norm = normalize_str(item.get("location", ""))
    if "remote" in work_mode or "ريموت" in work_mode:
        if any(r in eligible_regions or r in loc_norm for r in ["egypt", "مصر", "worldwide", "anywhere", "emea", "africa", "middle east"]):
            egypt_eligibility = "مؤكد: متاح من مصر"
        else:
            egypt_eligibility = "أهلية العمل من مصر محتاجة تحقق"
    else:
        egypt_eligibility = "مقر عمل داخل مصر" if any(c in loc_norm for c in ["cairo", "giza", "egypt", "القاهرة", "الجيزة", "مصر"]) else "محتاج تحقق"

    return {
        "first_published": item.get("first_published") or item.get("posted_at") or "تاريخ النشر غير مؤكد",
        "discovered_at": item.get("discovered_at") or check_time_iso,
        "last_verified": check_time_iso,
        "apply_state": apply_state,
        "apply_state_ar": apply_state_ar,
        "egypt_eligibility": egypt_eligibility,
        "is_repost_of_older": bool(item.get("original_post_date") and item.get("posted_at") and item["original_post_date"] != item["posted_at"]),
        "original_post_date": item.get("original_post_date")
    }


def evaluate_weekly_commute(location_raw: Optional[str], work_mode: Optional[str], onsite_days_per_week: Optional[int], company_shuttle: Optional[bool]) -> Dict:
    """Calculates realistic weekly commute burden from Shubra Masr factoring hybrid days & company shuttle."""
    mode = normalize_str(work_mode or "")
    loc = normalize_str(location_raw or "")

    if "remote" in mode or "ريموت" in mode:
        return {
            "score": 100,
            "one_way_min": 0,
            "days_per_week": 0,
            "weekly_hours": 0,
            "status": "CONFIRMED",
            "summary": "0 دقيقة (ريموت بالكامل)"
        }

    if not loc or loc in ("cairo", "egypt", "cairo egypt", "القاهرة", "مصر", "unknown"):
        return {
            "score": None,
            "one_way_min": None,
            "days_per_week": onsite_days_per_week,
            "weekly_hours": None,
            "status": "NEEDS_VERIFICATION",
            "summary": "العنوان الدقيق محتاج تحقق"
        }

    matched_zone = None
    for z_key, z_val in COMMUTE_ZONES.items():
        if z_key in loc:
            matched_zone = z_val
            break

    if not matched_zone:
        return {
            "score": None,
            "one_way_min": None,
            "days_per_week": onsite_days_per_week,
            "weekly_hours": None,
            "status": "NEEDS_VERIFICATION",
            "summary": "العنوان الدقيق محتاج تحقق"
        }

    one_way_min, transfers, route_desc = matched_zone
    days = onsite_days_per_week if onsite_days_per_week is not None else (3 if "hybrid" in mode else 5)
    weekly_hours = round((one_way_min * 2 * days) / 60.0, 1)

    # Score based on weekly commute load + shuttle support
    if one_way_min <= 35:
        score = 92
    elif one_way_min <= 55:
        score = 80
    elif one_way_min <= 85:
        # 80 min 1 day/week is very manageable (~2.7 hrs/week) vs 5 days/week (~13.3 hrs/week)
        if days <= 2:
            score = 78
        elif company_shuttle:
            score = 72
        else:
            score = 54
    else:
        score = 58 if (days <= 1 and company_shuttle) else 35

    if company_shuttle and score < 90:
        score = min(92, score + 8)

    days_label = f"{days} أيام/أسبوع" if days >= 3 else f"{days} يوم/أسبوع"
    shuttle_label = " • باصات شركة متوفرة" if company_shuttle else ""
    return {
        "score": score,
        "one_way_min": one_way_min,
        "transfers": transfers,
        "days_per_week": days,
        "weekly_hours": weekly_hours,
        "status": "CONFIRMED",
        "summary": f"~{one_way_min} د اتجاه واحد ({days_label} = {weekly_hours} س/أسبوع) • {route_desc}{shuttle_label}"
    }


def evaluate_evidence_fit(job: Dict) -> Dict:
    """
    Separates Required vs Bonus skills, checks fresh-grad overrides, and guards against sparse descriptions.
    """
    req_text = normalize_str(job.get("required_text", "") + " " + job.get("tasks", ""))
    bonus_text = normalize_str(job.get("bonus_text", ""))
    title_text = normalize_str(job.get("title", ""))
    combined = f"{title_text} {req_text} {bonus_text}".strip()

    # Sparse description guard (#15)
    if len(combined.split()) < 6:
        return {
            "score": None,
            "confidence": "LOW_EVIDENCE",
            "summary": "الأدلة قليلة — الوصف مختصر جدًا ويحتاج مراجعة الإعلان الأصلي",
            "evidence_pairs": [],
            "recommended_project": "DEPI Digital Payments Data Analysis (Python, SQL, Tableau)"
        }

    # Sales / Cold-Calling / Data-Entry Trap Guard
    traps = ["cold calling", "telesales", "field sales", "مبيعات ميدانية", "تلي سيلز", "commission only", "data entry only", "إدخال بيانات فقط"]
    for t in traps:
        if t in combined:
            return {
                "score": 25,
                "confidence": "HIGH",
                "summary": f"تحذير مهام: الدور يعتمد على ({t}) وليس تحليل بيانات حقيقي",
                "evidence_pairs": [{"req": f"مهام الإعلان: {t}", "cv": "غير متوافق مع مسار تحليل البيانات", "type": "TRAP"}],
                "recommended_project": "—"
            }

    skill_map = [
        ("sql", ["sql", "sql server", "mysql", "queries", "database", "erd"], 16),
        ("power_bi", ["power bi", "dax", "bi", "dashboard", "dashboards", "kpi"], 18),
        ("excel_vba", ["excel", "vba", "power query", "pivot", "reporting", "mis", "sfe"], 18),
        ("python", ["python", "pandas", "numpy", "eda"], 12),
        ("tableau", ["tableau", "visualization"], 10),
        ("ba_sa", ["business analysis", "systems analysis", "requirements", "uml", "operations"], 14)
    ]

    score = 16
    evidence_pairs = []

    for sk_key, keywords, pts in skill_map:
        in_req = any(has_word(req_text, k) or has_word(title_text, k) for k in keywords)
        in_bonus = any(has_word(bonus_text, k) for k in keywords)
        if in_req:
            score += pts
            evidence_pairs.append({
                "req": f"شرط أساسي: {PETER_CV_EVIDENCE[sk_key]['label']}",
                "cv": f"دليل مثبت: {PETER_CV_EVIDENCE[sk_key]['evidence']}",
                "type": "REQUIRED_MATCH"
            })
        elif in_bonus:
            score += int(pts * 0.6)
            evidence_pairs.append({
                "req": f"ميزة إضافية (Bonus): {PETER_CV_EVIDENCE[sk_key]['label']}",
                "cv": f"دليل مثبت: {PETER_CV_EVIDENCE[sk_key]['evidence']}",
                "type": "BONUS_MATCH"
            })

    # Fresh graduate explicit acceptance overrides preferred 1-year experience (#16)
    fresh_explicit = any(has_word(combined, k) for k in ["fresh", "graduate", "graduates", "intern", "internship", "0 1", "حديثي التخرج", "تدريب"])
    asks_1_2_yr = any(k in combined for k in ["1 year", "1 2 years", "سنة خبرة"])
    asks_3_plus = any(k in combined for k in ["3 years", "4 years", "5 years", "senior", "خبرة 3", "خبرة 5"])

    if fresh_explicit:
        score += 12
        evidence_pairs.append({
            "req": "قبول حديثي التخرج / التدريب مصرّح به في الإعلان",
            "cv": PETER_CV_EVIDENCE["fresh_grad"]["evidence"],
            "type": "REQUIRED_MATCH"
        })
    elif asks_1_2_yr:
        evidence_pairs.append({
            "req": "يطلب 1 سنة خبرة (بدون استثناء صريح للفريش)",
            "cv": "تحتاج إبراز مشاريع العمل الحر (3+ مشاريع) وتدريبات DEPI وNTI كخبرة عملية",
            "type": "GAP_REVIEW"
        })
    elif asks_3_plus:
        score -= 35
        evidence_pairs.append({
            "req": "يطلب خبرة +3 سنوات",
            "cv": "أعلى من مستوى خريج 2026 — شرط غير مستوفى",
            "type": "GAP_HARD"
        })

    # Select best CV project to highlight (#25)
    if any(k in combined for k in ["payment", "fintech", "bank", "transaction", "مدفوعات", "بنك"]):
        rec_proj = "Digital Payments Data Analysis (DEPI Capstone — 5,000 transactions, Python, SQL, Tableau)"
    elif any(k in combined for k in ["sfe", "sales", "commercial", "kpi", "mis", "reporting"]):
        rec_proj = "Student Performance KPI Power BI Dashboard + Excel/VBA Event Automation System"
    else:
        rec_proj = "Graduation Project (A+ Lead System & Data Analyst) + FeeLink Web Platform"

    final_score = max(0, min(100, score))
    return {
        "score": final_score,
        "confidence": "HIGH",
        "summary": evidence_pairs[0]["req"] if evidence_pairs else "تطابق عام مع تخصص BIS",
        "evidence_pairs": evidence_pairs,
        "recommended_project": rec_proj
    }


def diagnose_missed_opportunity(post_text: str, post_url: str, post_timestamp_iso: Optional[str], search_audit_log: List[Dict]) -> Dict:
    """
    Compares a user-submitted missed post against actual search execution logs
    to find the exact verifiable reason it was missed and propose a measurable query patch (#4, #19).
    """
    norm_post = normalize_str(post_text)
    url_lower = (post_url or "").lower()

    # 1. Check if post was published AFTER the latest completed scan
    if post_timestamp_iso and search_audit_log:
        latest_run = search_audit_log[-1]
        if post_timestamp_iso > latest_run["completed_at"]:
            return {
                "reason_code": "TIMING_WINDOW",
                "verifiable_finding": f"المصدر اتفحص الساعة {latest_run['completed_at']} قبل نشر البوست ({post_timestamp_iso}).",
                "proposed_patch": "لا يلزم تعديل — ستُلتقط تلقائيًا في الجولة الساعية القادمة بنافذة التداخل (90 دقيقة).",
                "patch_keyword": None
            }

    # 2. Check if source requires authenticated feed access
    if "linkedin.com/feed/update" in url_lower or "facebook.com" in url_lower:
        return {
            "reason_code": "GATED_FEED_SOURCE",
            "verifiable_finding": "الرابط من خلاصة حساب مغلقة (Authenticated Feed) غير متاحة للزحف العام بدون تسجيل دخول.",
            "proposed_patch": "متابعة اسم الناشر/الشركة في البحث العام + الاعتماد على زر «شارك مع الرادار» أو تنبيهات Gmail.",
            "patch_keyword": "recruiter_public_xray"
        }

    # 3. Check Query Keyword Gap against executed queries in search_audit_log
    executed_queries = " ".join(q for run in search_audit_log for q in run.get("queries_executed", [])).lower()
    synonym_checks = [
        ("sales force effectiveness", "sfe", 'إضافة "Sales Force Effectiveness" بجانب "SFE"'),
        ("commercial excellence", "sfe", 'إضافة "Commercial Excellence" لمسار SFE'),
        ("revenue operations", "sales operations", 'إضافة "Revenue Operations" لمسار العمليات'),
        ("performance reporting", "reporting", 'إضافة "Performance Reporting" لمسار التقارير'),
        ("تقارير مبيعات", "sales", 'إضافة المصطلح العربي "تقارير مبيعات" للاستعلامات العربية')
    ]
    for phrase, short_kw, patch_desc in synonym_checks:
        if phrase in norm_post and phrase not in executed_queries:
            return {
                "reason_code": "QUERY_SYNONYM_GAP",
                "verifiable_finding": f'الاستعلامات المنفذة كانت تبحث عن "{short_kw.upper()}" فقط، بينما نص البوست استخدم "{phrase}" بدون الاختصار.',
                "proposed_patch": patch_desc,
                "patch_keyword": phrase
            }

    return {
        "reason_code": "INSUFFICIENT_LOG_EVIDENCE",
        "verifiable_finding": "السبب غير متاح بدقة من سجل البحث الحالي (قد يكون البوست غير مفهرس بعد في محركات البحث).",
        "proposed_patch": "إضافة الشركة لقائمة المتابعة المباشرة وفحص صفحتها في الجولة القادمة.",
        "patch_keyword": "company_direct_watch"
    }
