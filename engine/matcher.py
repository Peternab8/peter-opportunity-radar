import hashlib
import re
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

PRIORITY_THRESHOLD = 80

PETER_CV_EVIDENCE = {
    "sql": {
        "label": "SQL & قواعد البيانات العلائقية",
        "evidence": "تصميم قاعدة بيانات 6+ كيانات (ERD) في مشروع NTI + تحليل 5,000 معاملة دفع رقمي بـ SQL"
    },
    "power_bi": {
        "label": "Power BI & لوحات المؤشرات",
        "evidence": "بناء KPI Dashboard تفاعلية لمشروع أداء الطلاب (1,000+ سجل) وتدريب NTI (120 ساعة)"
    },
    "dashboard_generic": {
        "label": "تصميم لوحات المتابعة والتقارير (Dashboards)",
        "evidence": "خبرة عملية في بناء لوحات تفاعلية عبر Power BI وTableau وExcel"
    },
    "tableau": {
        "label": "Tableau & تصور البيانات",
        "evidence": "لوحة Tableau من 5+ رسوم بيانية لمشروع التخرج في مبادرة DEPI"
    },
    "excel_vba": {
        "label": "Excel المتقدم وPower Query وVBA",
        "evidence": "نظام حجز فعاليات فعلي بـ Excel/VBA وأتمتة رسائل التأكيد لـ 500–1,000 مشارك"
    },
    "python": {
        "label": "Python (Pandas / NumPy / EDA)",
        "evidence": "تنظيف وتحليل استكشافي (EDA) لـ 5,000 معاملة في DEPI و1,000 سجل طلاب في NTI"
    },
    "ba_sa": {
        "label": "تحليل الأعمال والنظم (Business & Systems Analysis)",
        "evidence": "قائد تحليل النظم والبيانات بمشروع التخرج BIS حلوان (امتياز A+) + منصة FeeLink"
    },
    "sfe_ops": {
        "label": "متابعة الأداء والتقارير التجارية (SFE / Operations)",
        "evidence": "خبرة في إعداد تقارير الأداء ولوحات KPIs وأتمتة الجداول التشغيلية"
    },
    "fresh_grad": {
        "label": "بكالوريوس BIS حلوان 2026 (امتياز مع مرتبة الشرف GPA 3.67)",
        "evidence": "خريج حديث مع 3+ مشاريع تحليل بيانات وتدريبات CIB وبنك القاهرة والبنك المركزي"
    }
}

COMMUTE_ESTIMATES = {
    "shubra masr": (15, "شبرا مصر · حوالي ١٥ دقيقة"),
    "ramses": (20, "رمسيس · حوالي ٢٠ دقيقة من شبرا (مترو خط ٢ مباشر)"),
    "downtown": (25, "وسط البلد · حوالي ٢٥ دقيقة من شبرا (مترو خط ٢ مباشر)"),
    "shubra el kheima": (20, "شبرا الخيمة · حوالي ٢٠ دقيقة (مترو خط ٢ مباشر)"),
    "dokki": (30, "الدقي · حوالي ٣٠ دقيقة من شبرا (مترو خط ٢ مباشر)"),
    "mohandessin": (40, "المهندسين · حوالي ٤٠ دقيقة من شبرا"),
    "giza": (38, "الجيزة · حوالي ٣٨ دقيقة من شبرا (مترو خط ٢ مباشر)"),
    "zamalek": (35, "الزمالك · حوالي ٣٥ دقيقة من شبرا"),
    "heliopolis": (45, "مصر الجديدة · حوالي ٤٥ دقيقة من شبرا"),
    "nasr city": (52, "مدينة نصر · حوالي ٥٢ دقيقة من شبرا"),
    "maadi": (55, "المعادي · حوالي ٥٥ دقيقة من شبرا"),
    "smart village": (80, "القرية الذكية · حوالي ٨٠ دقيقة من شبرا"),
    "6th of october": (85, "٦ أكتوبر · حوالي ٨٥ دقيقة من شبرا"),
    "new cairo": (78, "القاهرة الجديدة · حوالي ٧٨ دقيقة من شبرا"),
    "fifth settlement": (78, "التجمع الخامس · حوالي ٧٨ دقيقة من شبرا"),
    "sheikh zayed": (75, "الشيخ زايد · حوالي ٧٥ دقيقة من شبرا"),
    "new administrative capital": (105, "العاصمة الإدارية · حوالي ١٠٥ دقائق من شبرا")
}

ACCOUNTING_CORE_RX = re.compile(
    r"\b(general ledger|gl accountant|accounts payable|accounts receivable|bookkeeper|bookkeeping|auditor|external audit|internal audit|tax specialist|tax accountant|cost accountant|financial accounting|قيود يومية|تسويات بنكية|إقفال شهري|محاسب عام|محاسب ضرائب|مراجع حسابات)\b",
    re.I
)

SALES_TRAP_RX = re.compile(
    r"\b(cold calling|telesales|tele-sales|outdoor sales|field sales|door to door|real estate broker|commission only|مبيعات ميدانية|تلي سيلز|تسويق عقاري)\b",
    re.I
)

CLOSED_PHRASES = [
    "no longer accepting applications",
    "this job is closed",
    "position has been filled",
    "job is no longer available",
    "expired",
    "تم إغلاق التقديم",
    "انتهى التقديم",
    "الوظيفة مغلقة",
]


def normalize_str(s: Optional[str]) -> str:
    if not s:
        return ""
    s = str(s).lower().strip()
    s = re.sub(r"[^a-z0-9\u0600-\u06FF\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def canonicalize_url(url: Optional[str]) -> str:
    if not url:
        return ""
    u = str(url).strip().split("#")[0]
    if "?" in u:
        base, qs = u.split("?", 1)
        # Keep meaningful ID params if present, drop tracking utm params
        kept = [p for p in qs.split("&") if not p.lower().startswith(("utm_", "trk", "ref", "fbclid", "gclid"))]
        u = f"{base}?{'&'.join(kept)}" if kept else base
    return u.rstrip("/").lower()


def extract_district_token(location_raw: Optional[str]) -> str:
    loc = normalize_str(location_raw)
    if not loc:
        return "unknown_loc"
    for zone in COMMUTE_ESTIMATES.keys():
        if zone in loc:
            return zone.replace(" ", "_")
    # Fallback to first meaningful city/district token
    tokens = [t for t in loc.split() if t not in {"egypt", "مصر", "governorate", "محافظة"}]
    return "_".join(tokens[:2]) if tokens else "unknown_loc"


def compute_job_identity(
    company: Optional[str],
    title: Optional[str],
    req_id: Optional[str] = None,
    location: Optional[str] = None,
    canonical_url: Optional[str] = None
) -> Tuple[str, str]:
    """
    Point 22: Deduplication priority:
    1) Company + Requisition ID
    2) Company + Canonical URL
    3) Company + Core Title + Normalized District/Location (Maadi != Giza)
    Also returns a loose family_id to flag 'محتمل نفس الإعلان' when locations differ.
    """
    co = normalize_str(company) or "unknown_company"
    noise = {"urgent", "hiring", "immediate", "for", "and", "the", "a", "مطلوب", "فورا"}
    core_tokens = sorted(set(t for t in normalize_str(title).split() if t not in noise))
    clean_title = " ".join(core_tokens) or "untitled_role"
    loc_token = extract_district_token(location)

    if req_id and normalize_str(req_id):
        exact_raw = f"{co}::req::{normalize_str(req_id)}"
    elif canonical_url and canonicalize_url(canonical_url):
        exact_raw = f"{co}::url::{canonicalize_url(canonical_url)}"
    else:
        exact_raw = f"{co}::title::{clean_title}::loc::{loc_token}"

    exact_id = hashlib.sha256(exact_raw.encode("utf-8")).hexdigest()[:16]
    family_raw = f"{co}::family::{clean_title}"
    family_id = hashlib.sha256(family_raw.encode("utf-8")).hexdigest()[:12]
    return exact_id, family_id


def verify_receipt_and_status(item: Dict, check_time_iso: str) -> Dict:
    """
    Points 14 & 15:
    - Never fabricates missing publish dates or missing locations.
    - 'OPEN_VERIFIED' requires explicit apply evidence & no closed signal.
    - Detects generic company career homepages vs direct job postings.
    """
    body_lower = (str(item.get("page_body") or "") + " " + str(item.get("description") or "")).lower()
    http_status = item.get("http_status", 200)
    url = str(item.get("url") or "").strip()

    is_closed = http_status in (404, 410) or any(p in body_lower for p in CLOSED_PHRASES)

    # Detect generic company career page (e.g., apply.workable.com/company/ with no /j/job-id)
    is_company_page = False
    if url:
        u_clean = url.rstrip("/").lower()
        if re.search(r"(apply\.workable\.com/[^/]+|/careers|/jobs)$", u_clean) and "/j/" not in u_clean and "/view/" not in u_clean and "/jobs/p/" not in u_clean:
            is_company_page = True

    has_direct_apply = bool(
        item.get("has_apply_button")
        or item.get("apply_email")
        or re.search(r"(linkedin\.com/jobs/view/|wuzzuf\.net/jobs/p/|indeed\.com/viewjob|apply\.workable\.com/[^/]+/j/|jobs\.lever\.co/[^/]+/[^/]+|boards\.greenhouse\.io/[^/]+/jobs/)", url.lower())
    )

    if is_closed:
        apply_state = "CLOSED"
        apply_state_ar = "مغلق / منتهي"
        action_label = "الإعلان مغلق"
    elif is_company_page:
        apply_state = "NEEDS_VERIFICATION"
        apply_state_ar = "محتاج تحقق"
        action_label = "صفحة الشركة"
    elif has_direct_apply and url.startswith("http"):
        apply_state = "OPEN_VERIFIED"
        apply_state_ar = "مفتوح بدليل"
        action_label = "افتح التقديم"
    elif url.startswith("http"):
        apply_state = "NEEDS_VERIFICATION"
        apply_state_ar = "محتاج تحقق"
        action_label = "افتح الرابط"
    else:
        apply_state = "NEEDS_VERIFICATION"
        apply_state_ar = "محتاج تحقق"
        action_label = "تفاصيل"

    # Point 21: Remote & Egypt eligibility validation
    work_mode_raw = str(item.get("work_mode") or "").strip()
    mode_norm = normalize_str(work_mode_raw)
    loc_raw = str(item.get("location") or "").strip()
    loc_norm = normalize_str(loc_raw)
    eligible_norm = normalize_str(str(item.get("eligible_regions") or ""))
    full_geo = f"{loc_norm} {eligible_norm} {body_lower}"

    if "remote" in mode_norm or "ريموت" in mode_norm or "عن بعد" in mode_norm:
        has_egypt_ok = any(k in full_geo for k in ["egypt", "مصر", "worldwide", "anywhere", "emea", "africa", "middle east", "mena"])
        has_exclusion = any(k in full_geo for k in ["us only", "usa only", "uk only", "eu only", "canada only", "must reside in the us", "united states only"])
        if has_egypt_ok and not has_exclusion:
            egypt_eligibility = "مؤكد: متاح من مصر"
            egypt_status = "CONFIRMED"
        else:
            egypt_eligibility = "مصر محتاجة تأكيد"
            egypt_status = "NEEDS_CONFIRMATION"
    elif any(k in loc_norm for k in ["egypt", "cairo", "giza", "alexandria", "مصر", "القاهرة", "الجيزة", "المعادي", "الدقي", "أكتوبر", "التجمع"]):
        egypt_eligibility = "مؤكد: داخل مصر"
        egypt_status = "CONFIRMED"
    elif not loc_raw:
        egypt_eligibility = "العنوان غير مذكور"
        egypt_status = "UNKNOWN"
    else:
        egypt_eligibility = "مصر محتاجة تأكيد"
        egypt_status = "NEEDS_CONFIRMATION"

    # Point 15: Never substitute today's date when first_published is unknown
    first_pub = item.get("first_published") or item.get("posted_at")
    if first_pub and str(first_pub).strip():
        first_pub_clean = str(first_pub).strip()
    else:
        first_pub_clean = None

    return {
        "first_published": first_pub_clean,
        "discovered_at": item.get("discovered_at") or check_time_iso,
        "last_verified": check_time_iso,
        "apply_state": apply_state,
        "apply_state_ar": apply_state_ar,
        "action_label": action_label,
        "is_company_page": is_company_page,
        "egypt_eligibility": egypt_eligibility,
        "egypt_status": egypt_status,
    }


def evaluate_weekly_commute(
    location_raw: Optional[str],
    work_mode_raw: Optional[str],
    onsite_days_per_week: Optional[int] = None,
    egypt_status: str = "UNKNOWN"
) -> Dict:
    """
    Points 15, 20, 21:
    - Treats commute as an estimate from Shubra Masr.
    - Unknown office days remain unknown (never assumes 3 or 5 days).
    - Remote gets 'بدون مشوار' ONLY when Egypt eligibility is confirmed.
    """
    mode = normalize_str(work_mode_raw)
    loc = normalize_str(location_raw)

    if "remote" in mode or "ريموت" in mode or "عن بعد" in mode:
        if egypt_status == "CONFIRMED":
            return {
                "score": 100,
                "one_way_min": 0,
                "days_per_week": 0,
                "status": "CONFIRMED",
                "summary": "بدون مشوار (ريموت متاح من مصر)"
            }
        return {
            "score": None,
            "one_way_min": 0,
            "days_per_week": 0,
            "status": "NEEDS_CONFIRMATION",
            "summary": "ريموت · مصر محتاجة تأكيد"
        }

    if not loc:
        return {
            "score": None,
            "one_way_min": None,
            "days_per_week": onsite_days_per_week,
            "status": "UNKNOWN",
            "summary": "العنوان غير مذكور"
        }

    matched_zone = None
    for z_key, z_val in COMMUTE_ESTIMATES.items():
        if z_key in loc:
            matched_zone = z_val
            break

    if not matched_zone:
        if any(k in loc for k in ["cairo", "egypt", "القاهرة", "مصر"]):
            return {
                "score": None,
                "one_way_min": None,
                "days_per_week": onsite_days_per_week,
                "status": "NEEDS_DISTRICT",
                "summary": "القاهرة · الحي غير مذكور (تقدير المشوار محتاج تأكيد)"
            }
        return {
            "score": None,
            "one_way_min": None,
            "days_per_week": onsite_days_per_week,
            "status": "UNKNOWN",
            "summary": f"{location_raw} · تقدير المشوار محتاج تأكيد"
        }

    one_way_min, est_label = matched_zone
    if one_way_min <= 35:
        base_score = 92
    elif one_way_min <= 55:
        base_score = 80
    elif one_way_min <= 85:
        base_score = 62 if (onsite_days_per_week is not None and onsite_days_per_week <= 2) else 52
    else:
        base_score = 38

    if onsite_days_per_week is not None:
        days_note = f"حضور {onsite_days_per_week} أيام/أسبوع"
    else:
        days_note = "أيام المكتب محتاجة تأكيد"

    return {
        "score": base_score,
        "one_way_min": one_way_min,
        "days_per_week": onsite_days_per_week,
        "status": "ESTIMATED",
        "summary": f"تقدير: {est_label} · {days_note}"
    }


def split_sentences(text: str) -> List[str]:
    if not text:
        return []
    raw_parts = re.split(r"(?<=[.!؟\n])\s+|\s*[•\-–]\s+", str(text))
    return [p.strip() for p in raw_parts if len(p.strip()) >= 4]


def resolve_experience_precedence(combined_text: str) -> Tuple[Optional[int], bool, Optional[str]]:
    """
    Point 18: Resolves the STRONGEST mandatory experience requirement before scoring.
    Example: '1 year preferred' + '5 years required' -> mandatory_years = 5 (NOT 1).
    Preserves explicit fresh-grad acceptance only when not overridden by a hard 3+ yr requirement.
    """
    sentences = split_sentences(combined_text)
    max_mandatory_years = 0
    mandatory_sentence = None
    preferred_years = 0
    fresh_explicit = False
    fresh_sentence = None

    for sent in sentences:
        s_low = sent.lower()
        is_preferred = any(w in s_low for w in ["preferred", "plus", "nice to have", "bonus", "مفضل", "يفضل"])
        is_mandatory = any(w in s_low for w in ["required", "must", "minimum", "at least", "mandatory", "مطلوب", "مطلوبة", "خبرة لا تقل"])

        # Match patterns like "5 years", "3+ years", "٥ سنين", "3 سنوات"
        yr_matches = re.findall(r"(\d+)\s*\+?\s*(?:years?|yrs?|سنين|سنوات|سنة)", s_low)
        arabic_num_map = {"٣": 3, "٤": 4, "٥": 5, "٦": 6, "٧": 7}
        for ar_digit, val in arabic_num_map.items():
            if re.search(ar_digit + r"\s*(?:سنين|سنوات)", s_low):
                yr_matches.append(str(val))

        for ym in yr_matches:
            yrs = int(ym)
            if is_preferred and not is_mandatory:
                preferred_years = max(preferred_years, yrs)
            else:
                if yrs > max_mandatory_years:
                    max_mandatory_years = yrs
                    mandatory_sentence = sent

        if any(k in s_low for k in ["fresh graduate", "fresh graduates", "entry level", "0-1 year", "0 - 1 year", "trainee", "internship", "حديثي التخرج", "حديث التخرج", "مطلوب فريش"]):
            fresh_explicit = True
            fresh_sentence = sent

    if max_mandatory_years >= 3:
        return max_mandatory_years, False, mandatory_sentence
    if fresh_explicit:
        return 0, True, fresh_sentence
    if max_mandatory_years > 0:
        return max_mandatory_years, False, mandatory_sentence
    if preferred_years > 0:
        return None, False, None
    return None, False, None


def evaluate_evidence_fit(job: Dict) -> Dict:
    """
    Points 13, 16, 17, 18, 19:
    - Never uses a default 85% score.
    - Filters role core BEFORE scoring skills (e.g., Accounting/GL goes low even with Excel;
      Sales Support with KPIs/Reporting for junior rises).
    - Extracts original source sentence for each matched evidence pair.
    - Distinguishes 'شرط أساسي' vs 'ميزة إضافية'.
    """
    title_raw = str(job.get("title") or "").strip()
    desc_raw = str(job.get("required_text") or "") + " " + str(job.get("tasks") or "") + " " + str(job.get("bonus_text") or "")
    full_raw = f"{title_raw}. {desc_raw}".strip()
    full_norm = normalize_str(full_raw)

    # Sparse description guard (Point 17)
    if len(full_norm.split()) < 6:
        return {
            "score": None,
            "confidence": "LOW_EVIDENCE",
            "role_core": "SPARSE",
            "has_mandatory_conflict": False,
            "reason_first": "الأدلة قليلة — النص مختصر جدًا ويحتاج فتح الإعلان الأصلي",
            "caveat_first": "الوصف لا يكفي لحساب درجة ملاءمة",
            "evidence_pairs": [],
            "recommended_project": "مشروع DEPI لتحليل المدفوعات الرقمية (Python, SQL, Tableau)"
        }

    # Point 16: Role-Core Filter BEFORE Skill Scoring
    if SALES_TRAP_RX.search(full_raw):
        return {
            "score": 18,
            "confidence": "HIGH",
            "role_core": "SALES_TRAP",
            "has_mandatory_conflict": True,
            "reason_first": "دور مبيعات مباشرة / مكالمات وليس تحليل بيانات",
            "caveat_first": "تم خفض الأولوية لتعارض جوهر المهام",
            "evidence_pairs": [{"tag": "تعارض دور", "quote": title_raw, "cv": "خارج مسار تحليل البيانات والتقارير"}],
            "recommended_project": "—"
        }

    if ACCOUNTING_CORE_RX.search(full_raw) and not re.search(r"\b(bi analyst|data analyst|business intelligence|sfe)\b", title_raw, re.I):
        return {
            "score": 32,
            "confidence": "HIGH",
            "role_core": "ACCOUNTING_LOW_PRIORITY",
            "has_mandatory_conflict": True,
            "reason_first": "محاسبة مالية وقيود وإقفال شهري · أولوية منخفضة لملف BIS/BI",
            "caveat_first": "وجود Excel لا يحوّل الدور إلى تحليل بيانات",
            "evidence_pairs": [{"tag": "جوهر الدور", "quote": title_raw, "cv": "دور محاسبي تقليدي خارج مسار BI/Data"}],
            "recommended_project": "—"
        }

    # Point 18: Resolve strongest mandatory experience first
    mandatory_years, fresh_explicit, exp_quote = resolve_experience_precedence(full_raw)
    if mandatory_years is not None and mandatory_years >= 3:
        return {
            "score": 30,
            "confidence": "HIGH",
            "role_core": "SENIOR_EXPERIENCE_CONFLICT",
            "has_mandatory_conflict": True,
            "reason_first": f"يتطلب خبرة إلزامية {mandatory_years} سنوات",
            "caveat_first": "شرط الخبرة أعلى من مستوى خريج ٢٠٢٦",
            "evidence_pairs": [{"tag": "شرط إلزامي", "quote": exp_quote or f"{mandatory_years} years required", "cv": "خريج ٢٠٢٦ (٠–١ سنة خبرة)"}],
            "recommended_project": "—"
        }

    # Extract sentence-level evidence (Point 17)
    sentences = split_sentences(full_raw)
    skill_rules = [
        ("sql", [r"\bsql\b", r"\bsql server\b", r"\bmysql\b", r"\bdatabase\b", r"\berd\b"], 17),
        ("power_bi", [r"\bpower\s*bi\b", r"\bdax\b"], 18),
        ("tableau", [r"\btableau\b"], 12),
        ("dashboard_generic", [r"\bdashboard", r"\bkpi\b", r"لوحات متابعة", r"مؤشرات أداء"], 12),
        ("excel_vba", [r"\bexcel\b", r"\bvba\b", r"\bpower query\b", r"\bpivot\b", r"تقارير"], 16),
        ("python", [r"\bpython\b", r"\bpandas\b", r"\bnumpy\b"], 13),
        ("sfe_ops", [r"\bsfe\b", r"sales force effectiveness", r"commercial excellence", r"sales support", r"operations analyst", r"متابعة أداء"], 16),
        ("ba_sa", [r"business analyst", r"systems analyst", r"business analysis", r"systems analysis", r"\buml\b"], 15),
    ]

    score = 22
    matched_keys = set()
    evidence_pairs = []
    reason_bits = []

    for sent in sentences:
        s_low = sent.lower()
        is_bonus = any(w in s_low for w in ["preferred", "plus", "nice to have", "bonus", "مفضل", "يفضل"])
        for sk_key, patterns, pts in skill_rules:
            if sk_key in matched_keys:
                continue
            # Do not add generic dashboard if Power BI or Tableau already matched
            if sk_key == "dashboard_generic" and ("power_bi" in matched_keys or "tableau" in matched_keys):
                continue
            if any(re.search(pat, s_low) for pat in patterns):
                matched_keys.add(sk_key)
                earned = int(pts * 0.65) if is_bonus else pts
                score += earned
                tag_label = "ميزة إضافية" if is_bonus else "شرط أساسي"
                evidence_pairs.append({
                    "tag": tag_label,
                    "quote": sent[:160],
                    "cv": PETER_CV_EVIDENCE[sk_key]["evidence"]
                })
                if len(reason_bits) < 2:
                    reason_bits.append(PETER_CV_EVIDENCE[sk_key]["label"])

    # Sales Support with KPIs/Reporting + Junior boost (Point 16)
    is_sales_support_kpi = bool(re.search(r"sales support", full_raw, re.I)) and bool({"excel_vba", "dashboard_generic", "power_bi", "sfe_ops"} & matched_keys)
    if is_sales_support_kpi:
        score += 12

    if fresh_explicit:
        score += 12
        evidence_pairs.append({
            "tag": "قبول فريش",
            "quote": (exp_quote or title_raw)[:160],
            "cv": PETER_CV_EVIDENCE["fresh_grad"]["evidence"]
        })

    if not evidence_pairs:
        return {
            "score": None,
            "confidence": "LOW_EVIDENCE",
            "role_core": "UNVERIFIED",
            "has_mandatory_conflict": False,
            "reason_first": "الأدلة قليلة — لم يذكر الإعلان مهارات أو مهام واضحة",
            "caveat_first": "راجع نص الإعلان الأصلي قبل التقديم",
            "evidence_pairs": [],
            "recommended_project": "مشروع DEPI لتحليل المدفوعات الرقمية (Python, SQL, Tableau)"
        }

    final_score = max(35, min(98, score))

    # Build human-first reason before score (Point 6)
    loc_hint = str(job.get("location") or "").strip()
    head_phrase = f"{title_raw}" + (f" ({loc_hint})" if loc_hint else "")
    skills_phrase = (" · ".join(reason_bits)) if reason_bits else "مهام تقارير وتحليل"
    reason_first = f"{head_phrase} · {skills_phrase}"

    if mandatory_years in (1, 2) and not fresh_explicit:
        caveat_first = f"يذكر خبرة {mandatory_years} سنة · أبرز مشاريع DEPI وNTI"
    elif fresh_explicit:
        caveat_first = "يقبل حديثي التخرج صراحة"
    else:
        caveat_first = "مستوى الخبرة غير محدد بدقة في النص"

    if any(k in full_norm for k in ["payment", "fintech", "bank", "transaction", "مدفوعات", "بنك"]):
        rec_proj = "مشروع DEPI لتحليل 5,000 معاملة دفع رقمي (Python, SQL, Tableau)"
    elif {"sfe_ops", "excel_vba", "dashboard_generic"} & matched_keys:
        rec_proj = "لوحة مؤشرات أداء الطلاب (Power BI) + نظام حجز الفعاليات (Excel/VBA)"
    else:
        rec_proj = "مشروع التخرج BIS حلوان (امتياز A+) + قاعدة بيانات NTI"

    return {
        "score": final_score,
        "confidence": "HIGH",
        "role_core": "DATA_BI_TARGET",
        "has_mandatory_conflict": False,
        "reason_first": reason_first,
        "caveat_first": caveat_first,
        "evidence_pairs": evidence_pairs,
        "recommended_project": rec_proj
    }


def diagnose_missed_opportunity(post_text: str, post_url: str, audit_logs: List[Dict]) -> Dict:
    """Point 36: Diagnoses why a user-shared post was missed using actual scan logs."""
    norm_post = normalize_str(post_text)
    url_low = (post_url or "").lower()

    if not norm_post and not url_low:
        return {
            "code": "UNKNOWN",
            "finding": "السبب مجهول — لم يتم إدخال نص أو رابط كافٍ للفحص.",
            "suggestion": "الصق نص البوست كاملًا لتشخيصه."
        }

    # Check if role/seniority rule would exclude it
    if ACCOUNTING_CORE_RX.search(post_text or ""):
        return {
            "code": "EXCLUDED_BY_ROLE_CORE",
            "finding": "تم استبعادها لأن جوهر المهام محاسبة/قيود وليست تحليل بيانات.",
            "suggestion": "لا يُنصح بتعديل الفلتر إلا إذا أردت متابعة وظائف المحاسبة."
        }

    man_yrs, _, _ = resolve_experience_precedence(post_text or "")
    if man_yrs is not None and man_yrs >= 3:
        return {
            "code": "EXCLUDED_BY_SENIORITY",
            "finding": f"تم استبعادها لأنها تشترط خبرة إلزامية {man_yrs} سنوات.",
            "suggestion": "الرادار مهيأ لحماية وقتك من الإعلانات التي تشترط +3 سنوات خبرة."
        }

    if "linkedin.com/feed/update" in url_low or "linkedin.com/posts" in url_low:
        return {
            "code": "GATED_FEED_OR_INDEX_DELAY",
            "finding": "بوستات الحسابات الشخصية في LinkedIn لا تفتح للسحب الآلي المباشر أو لم تُفهرس بعد.",
            "suggestion": "استخدم «أضف فرصة» للصق البوست أو حفظ صفحة الناشر لمتابعتها."
        }

    executed_queries = " ".join(q for run in audit_logs for q in run.get("queries_executed", [])).lower()
    synonyms = [
        ("commercial excellence", "Commercial Excellence"),
        ("sales force effectiveness", "Sales Force Effectiveness"),
        ("revenue operations", "Revenue Operations"),
        ("customer insights", "Customer Insights"),
    ]
    for phrase, label in synonyms:
        if phrase in norm_post and phrase not in executed_queries:
            return {
                "code": "KEYWORD_GAP",
                "finding": f'كلمات البحث في آخر جولة لم تشمل مصطلح "{label}".',
                "suggestion": f'أضف "{label}" إلى كلمات البحث ثم أعد اختبار نفس البوست.'
            }

    return {
        "code": "UNKNOWN_FROM_LOG",
        "finding": "السبب مجهول من سجل الجولة الحالية (قد يكون البوست نُشر بعد آخر تشغيل أو في مصدر غير مربوط).",
        "suggestion": "احفظ الفرصة يدويًا من «أضف فرصة» وتأكد من تفعيل تنبيهات البريد."
    }


def run_self_tests() -> None:
    """Point 13 & 40: Built-in verification suite run before every cloud publish."""
    # 1. Experience precedence: "1 year preferred" + "5 years required" MUST NOT pass
    exp_res = evaluate_evidence_fit({
        "title": "Data Analyst",
        "required_text": "1 year experience preferred. Minimum 5 years required in SQL and Python."
    })
    assert exp_res["score"] is not None and exp_res["score"] < 50, "Failed experience precedence test"

    # 2. Accounting role with Excel MUST be downgraded
    acc_res = evaluate_evidence_fit({
        "title": "General Ledger Accountant",
        "required_text": "Responsible for monthly closing, journal entries, and advanced Excel reconciliation."
    })
    assert acc_res["score"] is not None and acc_res["score"] < 45, "Failed accounting role filter test"

    # 3. Sales Support with KPIs & Junior MUST be promoted
    sfe_res = evaluate_evidence_fit({
        "title": "Sales Support & SFE Trainee",
        "required_text": "Fresh graduates welcome. Build daily KPI dashboards and sales reporting in Excel."
    })
    assert sfe_res["score"] is not None and sfe_res["score"] >= 70, "Failed SFE junior promotion test"

    # 4. Location-aware deduplication: Maadi vs Giza MUST produce distinct IDs
    id_maadi, fam_maadi = compute_job_identity("Paymob", "Junior Data Analyst", location="Maadi, Cairo")
    id_giza, fam_giza = compute_job_identity("Paymob", "Junior Data Analyst", location="Dokki, Giza")
    assert id_maadi != id_giza and fam_maadi == fam_giza, "Failed location-aware identity test"

    # 5. Missing location/date MUST NOT fabricate Cairo or today's date
    rec = verify_receipt_and_status({"url": "https://example.com/careers"}, "2026-11-23T20:00:00Z")
    assert rec["first_published"] is None and rec["egypt_eligibility"] == "العنوان غير مذكور", "Failed no-fabrication test"


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_self_tests()
        print("MATCHER_SELF_TESTS_PASSED")