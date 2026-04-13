from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    Book,
    EssayTopic,
    EssayTopicProgress,
    GrammarLessonProgress,
    GrammarLessonQuestion,
    PracticeSet,
    Subject,
    SubjectSectionEntry,
    Test,
)
from .selectors import (
    get_book_filter_config,
    get_dashboard_subject_cards,
    get_formula_entries,
    get_math_formula_quiz_payload,
    get_user_math_mistake_items,
    get_language_problem_filter_config,
    get_latest_dashboard_resources,
    get_ranking_queryset,
    get_statistics_payload,
    is_language_subject,
    get_subject_books,
    get_subject_peer_subjects,
    get_subject_practice_sets,
    get_subject_tests,
    get_user_profile_summary,
    get_user_subject_best_score,
)
from .services import (
    assign_free_subject as _assign_free_subject,
    ensure_default_subscription_plans as _ensure_default_subscription_plans,
    get_active_subscription_ids as _get_active_subscription_ids,
    get_effective_subject_level as _get_effective_subject_level,
    get_or_sync_profile as _get_or_sync_profile,
    get_safe_profile_photo_url as _get_safe_profile_photo_url,
    get_referral_plan_quote as _get_referral_plan_quote,
    get_referral_summary as _get_referral_summary,
    rebuild_user_statistics as _rebuild_user_statistics,
    get_subject_theme as _get_subject_theme,
    get_user_subject_access_rows as _get_user_subject_access_rows,
    get_user_progress_summary as _get_user_progress_summary,
    sidebar_context as _sidebar_context,
    user_can_access_subject as _user_can_access_subject,
    user_requires_free_subject_selection as _user_requires_free_subject_selection,
)
from .utils import (
    LEVEL_ORDER,
    calculate_essay_topic_xp,
    calculate_grammar_lesson_xp,
    get_level_info,
)


def _build_grammar_groups(entries, progress_map, allowed_levels, selected_level):
    groups = []
    for level in LEVEL_ORDER:
        if level not in allowed_levels:
            continue
        level_entries = [entry for entry in entries if entry.access_level == level]
        if not level_entries:
            continue
        completed_count = sum(
            1
            for entry in level_entries
            if progress_map.get(entry.id) and progress_map[entry.id].is_completed
        )
        groups.append(
            {
                "label": level,
                "count": len(level_entries),
                "completed_count": completed_count,
                "is_active": level == selected_level,
                "progress_percent": round((completed_count / len(level_entries)) * 100) if level_entries else 0,
            }
        )
    return groups


def _format_price_label(value):
    return f"{int(value or 0):,}".replace(",", " ") + " so'm"


def _build_grammar_points(entry):
    if not entry:
        return []

    body_sentences = [
        sentence.strip(" -")
        for sentence in entry.body.replace("\n", " ").split(".")
        if sentence.strip()
    ]
    points = []
    if entry.summary:
        points.append(entry.summary)
    if entry.usage_note:
        points.append(entry.usage_note)
    points.extend(body_sentences[:3])

    deduped = []
    seen = set()
    for item in points:
        normalized = item.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped[:2]


def _build_user_initials(display_name, username):
    source = (display_name or username or "?").strip()
    parts = [part for part in source.replace("_", " ").split() if part]
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[1][0]}".upper()
    return source[:2].upper()


def _build_grammar_lesson_rows(entries, progress_map):
    lesson_rows = []
    unlocked = True
    for entry in entries:
        progress = progress_map.get(entry.id)
        is_completed = bool(progress and progress.is_completed)
        is_available = unlocked
        lesson_rows.append(
            {
                "entry": entry,
                "is_completed": is_completed,
                "is_available": is_available,
                "progress": progress,
            }
        )
        if unlocked and not is_completed:
            unlocked = False

    return lesson_rows


def _split_chronology_lines(entry):
    if not entry or not entry.body:
        return []
    return [line.strip(" -") for line in entry.body.splitlines() if line.strip()]


def _is_math_subject(subject_name):
    return "matem" in (subject_name or "").lower()


def _get_workspace_section_catalog(subject_theme_key):
    return {
        "books": {
            "description": "Darsliklar, PDF resurslar va mavzu bo'yicha materiallar.",
            "cta": "Resurslarni ochish",
            "unit": "resurs",
            "empty_note": "Resurslar hali yuklanmagan.",
        },
        "formulas": {
            "description": "Qisqa formulalar, ishlatilish joyi va eslab qolish uchun tayanch blok.",
            "cta": "Formulalarni ko'rish",
            "unit": "formula",
            "empty_note": "Formulalar hali kiritilmagan.",
        },
        "formula-quiz": {
            "description": "Formulalar bo'yicha test uslubidagi savol-javob bloki: nomi, qo'llanish joyi va yozilishini tekshiradi.",
            "cta": "Savol-javobni ochish",
            "unit": "savol",
            "empty_note": "Formula savol-javob bo'limi uchun hali yetarli formula kiritilmagan.",
        },
        "problems": {
            "description": (
                "Misol, masala va nazorat bloklarini bitta erkin ishlash oqimida birlashtiradigan bo'lim."
                if subject_theme_key == "math"
                else "Test va mashqlarni bitta assessment oqimida ishlash bo'limi."
            ),
            "cta": "Setlarni ochish",
            "unit": "set",
            "empty_note": "Mashq setlari hali tayyor emas.",
        },
        "mistakes": {
            "description": "Oldingi xatolarni yig'ib, qayta ishlash uchun eng foydali blok.",
            "cta": "Xatolarni ko'rish",
            "unit": "xato",
            "empty_note": "Hozircha xatolar yig'ilmagan.",
        },
        "terms": {
            "description": "Atamalarni qisqa mazmun va to'liq izoh bilan takrorlash katalogi.",
            "cta": "Atamalarni ko'rish",
            "unit": "atama",
            "empty_note": "Atamalar hali kiritilmagan.",
        },
        "events": {
            "description": "Muhim sana va voqealarni testdan oldin bir oqimda ko'rib chiqing.",
            "cta": "Sanalarni ochish",
            "unit": "voqea",
            "empty_note": "Sanalar hali kiritilmagan.",
        },
        "chronology": {
            "description": "Davrlar va ketma-ket jarayonlarni preview hamda detail ko'rinishida o'rganing.",
            "cta": "Xronologiyani ko'rish",
            "unit": "bo'lim",
            "empty_note": "Xronologiya hali tayyor emas.",
        },
        "grammar": {
            "description": "Daraja bo'yicha darslar, mini test va progress bilan ishlaydigan grammar yo'li.",
            "cta": "Darslarni ochish",
            "unit": "dars",
            "empty_note": "Grammar darslari hali yo'q.",
        },
        "rules": {
            "description": "Qoidalarni tez takrorlash va misollar bilan ko'rish uchun referens blok.",
            "cta": "Qoidalarni ko'rish",
            "unit": "qoida",
            "empty_note": "Qoidalar hali qo'shilmagan.",
        },
        "essay": {
            "description": "Mavzu, tezis, outline va milliy sertifikat formatidagi esse yozish uchun tayyor ish nuqtalari.",
            "cta": "Esse bo'limini ochish",
            "unit": "mavzu",
            "empty_note": "Esse mavzulari hali qo'shilmagan.",
        },
        "extras": {
            "description": "Asosiy darsga yordam beradigan qo'shimcha izoh va materiallar.",
            "cta": "Qo'shimcha blokni ochish",
            "unit": "material",
            "empty_note": "Qo'shimcha materiallar hali yo'q.",
        },
        "ai": {
            "description": "Tushuntirish, xato tahlili va aqlli tavsiya shu bo'limga ulanadi.",
            "cta": "Tez orada",
            "unit": "funksiya",
            "empty_note": "MVPdan keyin ulanadi.",
        },
        "chat": {
            "description": "Mavzu bo'yicha tezkor savol-javob va yo'naltirish moduli shu yerda bo'ladi.",
            "cta": "Tez orada",
            "unit": "funksiya",
            "empty_note": "MVPdan keyin ulanadi.",
        },
    }


def _build_workspace_flow_steps(subject_theme_key):
    if subject_theme_key == "math":
        return [
            {
                "step": "01",
                "title": "Formulani ko'rib chiqing",
                "text": "Qisqa formula blokidan yozilish va ishlatilish joyini eslang.",
            },
            {
                "step": "02",
                "title": "Formula quiz bilan tekshiring",
                "text": "Izohga qarab formulani topib, yodlashni tez mustahkamlang.",
            },
            {
                "step": "03",
                "title": "Assessment blokini ishlang",
                "text": "Misol, masala va nazorat savollarini bitta oqimda ishlab chiqing.",
            },
            {
                "step": "04",
                "title": "Natijani tahlil qiling",
                "text": "Oxirida xatolar bo'limiga qaytib, qaysi savollarda qiynalganingizni tiklang.",
            },
        ]

    if subject_theme_key == "history":
        return [
            {
                "step": "01",
                "title": "Davrni tushunib oling",
                "text": "Avval xronologiya yoki voqealar blokidan umumiy oqimni ko'ring.",
            },
            {
                "step": "02",
                "title": "Atamalarni takrorlang",
                "text": "Muhim tushunchalarni qisqa mazmun bilan eslab chiqing.",
            },
            {
                "step": "03",
                "title": "Assessment blokini ishlang",
                "text": "Keyin mashqlar bo'limida xotira va bog'lanishni tekshiring.",
            },
        ]

    return [
        {
            "step": "01",
            "title": "Grammatik bazani oching",
            "text": "Darajangizga mos mavzuni tanlab, qoida va misol bilan tanishing.",
        },
        {
            "step": "02",
            "title": "Esse yoki qoida blokiga o'ting",
            "text": "Mavzuni yozuv, tezis va aniq struktura bilan mustahkamlang.",
        },
        {
            "step": "03",
            "title": "Assessment bilan tekshiring",
            "text": "Oxirida mashqlar bo'limi orqali natijani ko'ring va xatoni toping.",
        },
    ]


def _build_workspace_focus(subject_theme_key, section_totals):
    focus_candidates = {
        "math": [
            (
                "formulas",
                "Formulalar blokidan boshlang",
                "Asosiy formula va qoida ko'z oldida bo'lsa, keyingi mashq bloklari ancha samarali ishlaydi.",
            ),
            (
                "problems",
                "Amaliy setga o'ting",
                "Bir nechta misol yoki masala bilan formulani darhol ishlatib ko'ring.",
            ),
            (
                "problems",
                "Assessment blokiga o'ting",
                "Misol, masala va nazorat savollarini bitta joyda ishlab ritmni ushlang.",
            ),
        ],
        "history": [
            (
                "chronology",
                "Xronologiya oqimini oching",
                "Davr va ketma-ketlikni oldin ko'rsangiz, testdagi bog'lanishlar ancha ravshanlashadi.",
            ),
            (
                "terms",
                "Atamalarni takrorlang",
                "Qisqa kartalar bilan asosiy tushunchalarni tez tiklab oling.",
            ),
            (
                "problems",
                "Tarix mashqlariga o'ting",
                "Atama va yil savollarini bitta assessment oqimida ishlab chiqing.",
            ),
        ],
        "language": [
            (
                "grammar",
                "Grammar yo'lidan boshlang",
                "Darajangizga mos darsni ochib, qoida va mini test bilan ishlang.",
            ),
            (
                "essay",
                "Esse bo'limiga o'ting",
                "Mavzu, tezis va outline ustida ishlab yozish oqimini kuchaytiring.",
            ),
            (
                "problems",
                "Assessment blokini ishlang",
                "Mavzu ustida ishlagandan keyin amaliy savollar bilan natijani tekshiring.",
            ),
        ],
    }

    for section_key, title, description in focus_candidates.get(subject_theme_key, []):
        if section_totals.get(section_key, 0):
            return {
                "key": section_key,
                "title": title,
                "description": description,
                "count": section_totals.get(section_key, 0),
            }

    for fallback_key in ("problems", "books"):
        if section_totals.get(fallback_key, 0):
            return {
                "key": fallback_key,
                "title": "Shu bo'limdan boshlash mumkin",
                "description": "Hozir eng tayyor blokdan kirib, subject workspace ichida ritmni ushlab turing.",
                "count": section_totals.get(fallback_key, 0),
            }

    return {
        "key": "books",
        "title": "Workspace hali to'ldirilmoqda",
        "description": "Kontent kiritilgach shu sahifa foydalanuvchini kerakli blokka olib boradi.",
        "count": 0,
    }


def _build_workspace_module_cards(section_items, section_catalog, section_totals, section_previews, primary_key):
    cards = []
    for item in section_items:
        if item["key"] == "home":
            continue

        meta = section_catalog.get(item["key"], {})
        is_coming_soon = item["key"] in {"ai", "chat"}
        count = section_totals.get(item["key"], 0)
        preview = section_previews.get(item["key"], "")

        if is_coming_soon:
            status = "Coming soon"
            preview_text = meta.get("empty_note", "")
        elif count:
            status = f"{count} ta {meta.get('unit', 'material')}"
            preview_text = preview or meta.get("description", "")
        else:
            status = f"0 ta {meta.get('unit', 'material')}"
            preview_text = meta.get("empty_note", "")

        cards.append(
            {
                "key": item["key"],
                "label": item["label"],
                "description": meta.get("description", ""),
                "cta": meta.get("cta", "Ochish"),
                "status": status,
                "preview": preview_text,
                "is_primary": item["key"] == primary_key,
                "is_coming_soon": is_coming_soon,
            }
        )

    return cards


@login_required
def dashboard_view(request):
    sidebar = _sidebar_context(request.user)
    profile = sidebar["profile"]
    xp_summary = sidebar["xp_summary"]
    referral_summary = _get_referral_summary(request.user)
    referral_summary["share_url"] = request.build_absolute_uri(
        reverse("referral-entry", args=[referral_summary["referral_code"]])
    )
    selected_subject_id = request.GET.get("subject")
    subjects = get_dashboard_subject_cards(request.user)
    for subject in subjects:
        subject["is_selected"] = str(subject["id"]) == str(selected_subject_id)
    free_selection_required = _user_requires_free_subject_selection(request.user)

    if request.method == "POST":
        selected_subject_id = (request.POST.get("free_subject_id") or "").strip()
        if not free_selection_required:
            messages.error(request, "Free fan tanlash hozir kerak emas.")
            return redirect("dashboard")
        if not selected_subject_id.isdigit():
            messages.error(request, "Bitta fan tanlang.")
            return redirect("dashboard")
        subject = get_object_or_404(Subject, id=int(selected_subject_id))
        try:
            _assign_free_subject(request.user, subject)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return redirect("dashboard")
        messages.success(request, f"{subject.name} free fan sifatida biriktirildi.")
        return redirect("dashboard")

    latest_test, featured_book = get_latest_dashboard_resources()
    level_info = sidebar["level_info"]
    if profile.level != level_info["label"]:
        profile.level = level_info["label"]
        profile.save(update_fields=["level"])

    quick_actions = [
        "Fanlarni tekshirish va obunalarni ko'rish",
        "Testlar sahifasidan mashqni boshlash",
        "Kitoblar sahifasidan resurslarni ochish",
        "Tarix bo'yicha o'yinlarda tezkor takrorlash",
    ]
    hub_cards = [
        {
            "title": "Testlar / Mashqlar",
            "description": "Alohida sahifada barcha testlar, murakkablik va vaqt bo'yicha ko'rinadi.",
            "href": "tests",
            "meta": latest_test.title if latest_test else "Hali test qo'shilmagan",
        },
        {
            "title": "Kitoblar",
            "description": "PDF formatdagi resurslar va fan bo'yicha tavsiya qilingan materiallar.",
            "href": "books",
            "meta": featured_book.title if featured_book else "Hali kitob qo'shilmagan",
        },
        {
            "title": "Reyting",
            "description": "XP, ishlangan testlar va eng yaxshi foiz asosida umumiy foydalanuvchilar reytingi.",
            "href": "ranking",
            "meta": "Hamma uchun ochiq",
        },
        {
            "title": "O'yinlar",
            "description": "Tarix savollaridan yig'iladigan battle formatidagi mini o'yinlar bilan tezkor takrorlash.",
            "href": "games-hub",
            "meta": "Tarix jangi",
        },
    ]
    stats = [
        {
            "label": "Daraja",
            "value": level_info["label"],
            "hint": f'{level_info["xp"]} XP, keyingi bosqichgacha {level_info["xp_to_next"]} XP',
        },
        {
            "label": "Fanlar",
            "value": f"{len(subjects)} ta",
            "hint": "Dashboardda ko'rinayotgan yo'nalishlar soni",
        },
        {
            "label": "XP",
            "value": profile.xp,
            "hint": "Daraja yig'ilgan XP orqali o'sadi.",
        },
        {
            "label": "Referral",
            "value": f'{referral_summary["available_percent"]}%',
            "hint": "Keyingi pullik obuna uchun tayyor chegirma.",
        },
    ]
    free_subject_choices = [subject for subject in subjects if not subject["is_owned"]]
    context = {
        **sidebar,
        "stats": stats,
        "subjects": subjects,
        "hub_cards": hub_cards,
        "quick_actions": quick_actions,
        "referral_summary": referral_summary,
        "free_selection_required": free_selection_required,
        "free_subject_choices": free_subject_choices,
    }
    return render(request, "dashboard.html", context)


@login_required
@require_POST
def dismiss_beta_notice_view(request):
    request.session.pop("beta_trial_notice", None)
    request.session.pop("beta_trial_expires_at", None)
    return redirect("dashboard")


@login_required
def subject_workspace_view(request, subject_id, section=None):
    profile = _get_or_sync_profile(request.user)
    xp_summary = _get_user_progress_summary(request.user)
    level_info = get_level_info(profile.xp)
    subject = get_object_or_404(Subject.objects.annotate(test_count=Count("test")), id=subject_id)
    subject_level = _get_effective_subject_level(request.user, subject_id=subject.id, profile=profile)
    selected_grade = request.GET.get("grade", "").strip()

    if not _user_can_access_subject(request.user, subject.id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")

    current_section = section or request.GET.get("section", "home")
    subject_theme = _get_subject_theme(subject.name)
    is_math_subject = _is_math_subject(subject.name)
    allowed_sections = {"home", "books", "tests", "ai", "chat"} | {
        item["key"] for item in subject_theme["extra_sections"]
    }
    if current_section not in allowed_sections:
        raise Http404("Bunday bo'lim mavjud emas.")
    if current_section == "tests":
        return redirect("subject-workspace-section", subject_id=subject.id, section="problems")

    peer_subjects = get_subject_peer_subjects(request.user, subject.id)

    book_filter_config = get_book_filter_config(subject)
    allowed_book_filters = {choice[0] for choice in book_filter_config["choices"]}
    selected_book_grade = selected_grade if selected_grade in allowed_book_filters or selected_grade == "other" else None
    books = get_subject_books(subject, grade=selected_book_grade, limit=12)
    grade_filters = [{"value": "", "label": "Barchasi", "is_active": selected_grade == ""}]
    grade_filters.extend(
        {
            "value": value,
            "label": label,
            "is_active": selected_grade == value,
        }
        for value, label in book_filter_config["choices"]
    )
    grade_filters.append(
        {
            "value": "other",
            "label": "Boshqalar",
            "is_active": selected_grade == "other",
        }
    )
    selected_test_filter = (request.GET.get("test_filter") or "all").strip()
    if selected_test_filter not in {"all", "general", "terms", "years"}:
        selected_test_filter = "all"
    selected_problem_filter = (request.GET.get("problem_filter") or "all").strip()
    if selected_problem_filter not in {"all", "grammar", "literature"}:
        selected_problem_filter = "all"
    language_problem_filter_config = get_language_problem_filter_config()
    tests = get_subject_tests(
        request.user,
        subject,
        subject_level,
        limit=6,
        category_filter=selected_test_filter,
        content_filter=selected_problem_filter,
    )
    history_test_filters = [
        {"value": "all", "label": "Umumiy", "is_active": selected_test_filter == "all"},
        {"value": "terms", "label": "Atamalar bo'yicha", "is_active": selected_test_filter == "terms"},
        {"value": "years", "label": "Yillar bo'yicha", "is_active": selected_test_filter == "years"},
    ]
    practice_sets = get_subject_practice_sets(
        request.user,
        subject,
        subject_level,
        limit=12,
        content_filter=selected_problem_filter,
    )
    language_problem_filters = [
        {
            "value": value,
            "label": label,
            "is_active": selected_problem_filter == value,
        }
        for value, label in language_problem_filter_config["choices"]
    ]

    section_items = [
        {"key": "home", "label": "Asosiy menyu"},
        {"key": "books", "label": "Kitoblar"},
    ]
    section_items.extend(subject_theme["extra_sections"])
    section_items.extend(
        [
            {"key": "ai", "label": "Ai yordamchi"},
            {"key": "chat", "label": "Chat"},
        ]
    )
    for item in section_items:
        item["is_active"] = item["key"] == current_section

    user_subject_best = get_user_subject_best_score(request.user, subject)
    accessible_test_count = Test.objects.filter(subject=subject).count()
    total_books_count = Book.objects.filter(subject=subject).count()
    accessible_practice_count = PracticeSet.objects.filter(subject=subject).count()
    combined_problem_count = accessible_practice_count + accessible_test_count
    home_metrics = [
        {"label": "Joriy daraja", "value": subject_level, "hint": "Shu fan bo'yicha hozirgi bosqich"},
        {
            "label": "Assessment bloklari",
            "value": f"{combined_problem_count} ta",
            "hint": "Barcha darajadagi test va mashqlar bitta bo'limda ko'rinadi.",
        },
        {
            "label": "Eng yaxshi natija",
            "value": f"{user_subject_best}%" if user_subject_best else "Hali yo'q",
            "hint": "Shu fan bo'yicha eng yaxshi foiz",
        },
    ]
    formula_query = (request.GET.get("q") or "").strip()
    formula_filter = request.GET.get("formula_filter", "all")
    selected_formula_id = request.GET.get("formula", "").strip()
    formula_entries = get_formula_entries(subject, formula_query, formula_filter)
    selected_formula = None
    if current_section == "formulas" and formula_entries:
        if selected_formula_id.isdigit():
            selected_formula = next((entry for entry in formula_entries if entry.id == int(selected_formula_id)), None)
        if selected_formula is None:
            selected_formula = formula_entries[0]
    math_formula_quiz = []
    math_mistake_items = []
    if is_math_subject:
        math_formula_quiz = get_math_formula_quiz_payload(subject)
        math_mistake_items = get_user_math_mistake_items(
            request.user,
            subject,
            limit=12 if current_section == "mistakes" else 4,
        )

    history_query = (request.GET.get("q") or "").strip()
    history_page_obj = None
    grammar_progress_map = {}
    grammar_lesson_rows = []
    grammar_questions = []
    grammar_question_total = 0
    grammar_progress = None
    grammar_quiz_result = None
    grammar_selected_level = subject_level
    grammar_available_levels = []
    selected_reference_entry = None
    reference_page_obj = None
    reference_entries = []
    essay_progress_map = {}
    selected_essay_progress = None

    base_section_entries_queryset = SubjectSectionEntry.objects.filter(subject=subject, section_key=current_section)
    section_entries_queryset = base_section_entries_queryset
    if current_section in {"terms", "events", "chronology"} and history_query:
        section_entries_queryset = section_entries_queryset.filter(
            Q(title__icontains=history_query)
            | Q(summary__icontains=history_query)
            | Q(body__icontains=history_query)
        )
    section_entries = list(section_entries_queryset)
    if current_section in {"terms", "events"}:
        history_paginator = Paginator(section_entries, 20)
        history_page_number = request.GET.get("page") or 1
        history_page_obj = history_paginator.get_page(history_page_number)
        section_entries = list(history_page_obj.object_list)
    selected_history_entry = None
    selected_grammar_entry = None
    chronology_cards = []
    if current_section == "chronology":
        chronology_cards = [
            {
                "entry": entry,
                "preview_lines": _split_chronology_lines(entry)[:5],
                "line_count": len(_split_chronology_lines(entry)),
            }
            for entry in section_entries
        ]
    if current_section in {"terms", "events"} and section_entries:
        selected_entry_id = request.GET.get("entry", "").strip()
        if selected_entry_id.isdigit():
            selected_history_entry = next((entry for entry in section_entries if entry.id == int(selected_entry_id)), None)
        if selected_history_entry is None:
            selected_history_entry = section_entries[0]
    if current_section in {"rules", "extras"}:
        reference_paginator = Paginator(section_entries, 15)
        reference_page_number = request.GET.get("page") or 1
        reference_page_obj = reference_paginator.get_page(reference_page_number)
        reference_entries = list(reference_page_obj.object_list)
        selected_entry_id = request.GET.get("entry", "").strip()
        if selected_entry_id.isdigit():
            selected_reference_entry = next((entry for entry in reference_entries if entry.id == int(selected_entry_id)), None)
        if selected_reference_entry is None:
            selected_reference_entry = reference_entries[0] if reference_entries else None
    if current_section == "grammar" and section_entries:
        requested_grammar_level = (request.GET.get("grammar_level") or "").strip().replace(" ", "+")
        grammar_available_levels = [
            level
            for level in LEVEL_ORDER
            if any(entry.access_level == level for entry in section_entries)
        ]
        if grammar_available_levels:
            if requested_grammar_level in grammar_available_levels:
                grammar_selected_level = requested_grammar_level
            elif subject_level in grammar_available_levels:
                grammar_selected_level = subject_level
            else:
                grammar_selected_level = grammar_available_levels[0]

        grammar_progress_map = {
            progress.lesson_id: progress
            for progress in GrammarLessonProgress.objects.filter(
                user=request.user,
                lesson__in=section_entries,
            )
        }
        filtered_grammar_entries = [
            entry
            for entry in section_entries
            if entry.access_level == grammar_selected_level
        ]
        grammar_lesson_rows = _build_grammar_lesson_rows(filtered_grammar_entries, grammar_progress_map)
        selected_entry_id = request.GET.get("entry", "").strip()
        if selected_entry_id.isdigit():
            selected_row = next((row for row in grammar_lesson_rows if row["entry"].id == int(selected_entry_id)), None)
            if selected_row and selected_row["is_available"]:
                selected_grammar_entry = selected_row["entry"]
        if selected_grammar_entry is None:
            first_available_row = next((row for row in grammar_lesson_rows if row["is_available"]), None)
            selected_grammar_entry = first_available_row["entry"] if first_available_row else (
                filtered_grammar_entries[0] if filtered_grammar_entries else section_entries[0]
            )
        grammar_progress = grammar_progress_map.get(selected_grammar_entry.id)
        grammar_questions = list(selected_grammar_entry.grammar_questions.all()[:10])
        grammar_question_total = len(grammar_questions)

        if request.method == "POST" and request.POST.get("grammar_action") == "submit_quiz":
            selected_row = next((row for row in grammar_lesson_rows if row["entry"].id == selected_grammar_entry.id), None)
            if not selected_row or not selected_row["is_available"]:
                messages.error(request, "Bu dars hali ochilmagan.")
                return redirect(
                    f"{request.path}?grammar_level={grammar_selected_level}&entry={selected_grammar_entry.id}"
                )

            if not grammar_questions:
                messages.error(request, "Bu mavzu uchun mini test hali qo'shilmagan.")
                return redirect(f"{request.path}?grammar_level={grammar_selected_level}&entry={selected_grammar_entry.id}")

            correct_count = 0
            review_items = []
            for question in grammar_questions:
                selected_option = (request.POST.get(f"grammar_question_{question.id}") or "").strip().upper()
                is_correct = selected_option == question.correct_option
                if is_correct:
                    correct_count += 1
                review_items.append(
                    {
                        "prompt": question.prompt,
                        "selected": selected_option or "Belgilanmagan",
                        "correct": question.correct_option,
                        "is_correct": is_correct,
                        "explanation": question.explanation,
                    }
                )

            total_questions = len(grammar_questions)
            score = round((correct_count / total_questions) * 100) if total_questions else 0
            passed = score >= 80

            grammar_progress, _ = GrammarLessonProgress.objects.get_or_create(
                user=request.user,
                lesson=selected_grammar_entry,
            )
            previous_grammar_xp = grammar_progress.xp_awarded
            grammar_progress.last_score = score
            grammar_progress.best_score = max(grammar_progress.best_score, score)
            grammar_progress.attempts_count += 1
            if passed and not grammar_progress.is_completed:
                grammar_progress.is_completed = True
                grammar_progress.completed_at = timezone.now()
            grammar_progress.xp_awarded = calculate_grammar_lesson_xp(
                grammar_progress.best_score,
                selected_grammar_entry.access_level,
                grammar_progress.is_completed,
                grammar_progress.attempts_count > 0,
            )
            grammar_progress.save()
            xp_awarded = max(0, grammar_progress.xp_awarded - previous_grammar_xp)
            _rebuild_user_statistics(request.user)
            _get_or_sync_profile(request.user)

            grammar_progress_map[selected_grammar_entry.id] = grammar_progress
            grammar_lesson_rows = _build_grammar_lesson_rows(filtered_grammar_entries, grammar_progress_map)
            grammar_quiz_result = {
                "score": score,
                "correct_count": correct_count,
                "total_questions": total_questions,
                "passed": passed,
                "xp_awarded": xp_awarded,
                "review_items": review_items,
            }

    grammar_featured_count = sum(1 for entry in section_entries if entry.is_featured) if current_section == "grammar" else 0
    grammar_total_count = len(grammar_lesson_rows) if current_section == "grammar" else 0
    grammar_completed_count = (
        sum(1 for row in grammar_lesson_rows if row["is_completed"])
        if current_section == "grammar"
        else 0
    )
    grammar_progress_percent = (
        round((grammar_completed_count / grammar_total_count) * 100)
        if grammar_total_count
        else 0
    )
    grammar_groups = _build_grammar_groups(
        section_entries,
        grammar_progress_map,
        grammar_available_levels,
        grammar_selected_level,
    ) if current_section == "grammar" else []
    grammar_points = _build_grammar_points(selected_grammar_entry) if current_section == "grammar" else []
    essay_queryset = EssayTopic.objects.filter(subject=subject)
    essay_topics = []
    selected_essay_topic = None
    essay_page_obj = None
    if current_section == "essay":
        essay_progress_map = {
            progress.topic_id: progress
            for progress in EssayTopicProgress.objects.filter(
                user=request.user,
                topic__in=essay_queryset,
            )
        }
        essay_page_obj = Paginator(essay_queryset, 15).get_page(request.GET.get("essay_page") or 1)
        essay_topics = list(essay_page_obj.object_list)
        selected_essay_id = request.GET.get("essay")
        if selected_essay_id:
            selected_essay_topic = next(
                (topic for topic in essay_topics if str(topic.id) == str(selected_essay_id)),
                None,
            ) or essay_queryset.filter(id=selected_essay_id).first()
        if selected_essay_topic is None and essay_topics:
            selected_essay_topic = essay_topics[0]
        if selected_essay_topic is not None:
            selected_essay_progress = essay_progress_map.get(selected_essay_topic.id)

        if (
            request.method == "POST"
            and request.POST.get("essay_action") == "mark_complete"
            and selected_essay_topic is not None
        ):
            essay_progress, _ = EssayTopicProgress.objects.get_or_create(
                user=request.user,
                topic=selected_essay_topic,
            )
            previous_essay_xp = essay_progress.xp_awarded
            essay_progress.is_completed = True
            if essay_progress.completed_at is None:
                essay_progress.completed_at = timezone.now()
            essay_progress.xp_awarded = calculate_essay_topic_xp(
                selected_essay_topic.access_level,
                essay_progress.is_completed,
                selected_essay_topic.is_featured,
            )
            essay_progress.save()
            selected_essay_progress = essay_progress
            essay_progress_map[selected_essay_topic.id] = essay_progress
            earned_xp = max(0, essay_progress.xp_awarded - previous_essay_xp)
            _rebuild_user_statistics(request.user)
            _get_or_sync_profile(request.user)
            if earned_xp:
                messages.success(request, f"Esse mavzusi yakunlandi. +{earned_xp} XP qo'shildi.")
            else:
                messages.info(request, "Bu esse mavzusi allaqachon yakunlangan.")
            return redirect(
                f"{request.path}?essay={selected_essay_topic.id}&essay_page={essay_page_obj.number}"
            )

    essay_highlights = [
        {"value": "24 ball", "label": "maksimal yozma ish bahosi"},
        {"value": "12 mezon", "label": "tekshiruv markazidagi asosiy mezonlar"},
        {"value": "100+ so'z", "label": "minimum hajmga yaqin xavfsiz ritm"},
        {"value": "3 xatboshi", "label": "kirish, asosiy qism va xulosa"},
    ]
    essay_writing_steps = [
        {
            "step": "01",
            "title": "Pozitsiyani aniqlang",
            "text": "Mavzuga bir aniq nuqtayi nazar tanlang va uni boshidan oxirigacha ushlab boring.",
        },
        {
            "step": "02",
            "title": "Struktura tuzing",
            "text": "Kirish, asosiy qism va xulosani kamida 3 xatboshida tarqating.",
        },
        {
            "step": "03",
            "title": "Dalil bilan yoping",
            "text": "Har asosiy fikrga misol, kuzatuv yoki mantiqiy asos qo'shing.",
        },
        {
            "step": "04",
            "title": "Tinish va imloni tekshiring",
            "text": "Oxirida uslub, savodxonlik va mantiqiy bog'lanishni alohida ko'zdan kechiring.",
        },
    ]
    essay_exam_rules = [
        "Publitsistik uslubda, ravon va tushunarli yozing.",
        "Reja va epigrafni alohida yozmang, asosiy matnga o'ting.",
        "Hajmni 100+ so'z atrofida xavfsiz ushlang.",
        "Kamida 3 xatboshi bilan kirish, asosiy qism va xulosa quring.",
    ]
    essay_review_focus = [
        "Mavzu to'liq ochilganmi",
        "Fikrlar izchil bog'langanmi",
        "Dalillar yetarlimi",
        "Savodxonlik va tinish belgisi tozami",
    ]
    essay_self_check_cards = [
        {
            "title": "Mazmun va pozitsiya",
            "score": "0-6 ball",
            "text": "Mavzu aniq ochilganmi, pozitsiya ravshanmi va asosiy fikr esse davomida saqlanganmi.",
        },
        {
            "title": "Tuzilish va mantiq",
            "score": "0-6 ball",
            "text": "Kirish, asosiy qism va xulosa mantiqan ulanadimi, xatboshilar o'z o'rnida turibdimi.",
        },
        {
            "title": "Dalil va misollar",
            "score": "0-6 ball",
            "text": "Asosiy fikrlar quruq qolmay, misol, kuzatuv yoki ishonarli asos bilan yopilganmi.",
        },
        {
            "title": "Savodxonlik va uslub",
            "score": "0-6 ball",
            "text": "Imloviy, uslubiy va tinish belgisi xatolari fikrni buzmaydigan darajadami.",
        },
    ]
    essay_self_check_note = (
        "Bu rasmiy tekshiruv emas, lekin yozib bo'lgach 24 ballik ritmga yaqin ichki self-check sifatida ishlatishingiz mumkin."
    )
    combined_problem_items = []
    for practice_set in practice_sets:
        combined_problem_items.append(
            {
                "kind": "practice_set",
                "badge": "Mashq",
                "title": practice_set.title,
                "level": practice_set.get_difficulty_display(),
                "description": practice_set.description or "",
                "meta_line": " ".join(
                    item
                    for item in [
                        f"Kitob: {practice_set.source_book}." if practice_set.source_book else "",
                        f"Mavzu: {practice_set.topic}." if practice_set.topic else "",
                    ]
                    if item
                ),
                "stats": [
                    f"{practice_set.exercise_count} ta topshiriq",
                    (
                        f"Eng yaxshi: {practice_set.best_score}%"
                        if practice_set.best_score is not None
                        else "Eng yaxshi natija yo'q"
                    ),
                    (
                        f"Oxirgi: {practice_set.last_score}%"
                        if practice_set.last_score is not None
                        else "Hali ishlanmagan"
                    ),
                    f"{practice_set.attempts} ta urinish",
                ],
                "href": f"/practice/sets/{practice_set.id}/solve/?next={request.get_full_path()}",
                "cta": "Ishlash",
            }
        )
    for test in tests:
        combined_problem_items.append(
            {
                "kind": "test",
                "badge": "Assessment",
                "title": test.title,
                "level": test.display_difficulty,
                "description": "Timer yo'q. Savollarni bemalol ishlab, keyin natijani ko'ring.",
                "meta_line": f"{test.question_count} ta savol",
                "stats": [
                    "Erkin ishlash",
                    (
                        f"Eng yaxshi: {test.best_score}%"
                        if test.best_score is not None
                        else "Eng yaxshi natija yo'q"
                    ),
                    (
                        f"Oxirgi: {test.last_score}%"
                        if test.last_score is not None
                        else "Hali ishlanmagan"
                    ),
                    f"{test.attempts} ta urinish",
                ],
                "href": f"/tests/{test.id}/start/?next={request.get_full_path()}",
                "cta": "Boshlash",
            }
        )
    combined_problem_items.sort(
        key=lambda item: (
            LEVEL_ORDER.index(item["level"]) if item["level"] in LEVEL_ORDER else len(LEVEL_ORDER),
            item["badge"] != "Mashq",
            item["title"].lower(),
        )
    )
    section_catalog = _get_workspace_section_catalog(subject_theme["key"])
    section_totals = {
        "books": total_books_count,
        "tests": accessible_test_count,
        "formulas": SubjectSectionEntry.objects.filter(subject=subject, section_key="formulas").count(),
        "formula-quiz": len(math_formula_quiz) if is_math_subject else 0,
        "problems": combined_problem_count,
        "mistakes": len(math_mistake_items) if is_math_subject else 0,
        "terms": SubjectSectionEntry.objects.filter(subject=subject, section_key="terms").count(),
        "events": SubjectSectionEntry.objects.filter(subject=subject, section_key="events").count(),
        "chronology": SubjectSectionEntry.objects.filter(subject=subject, section_key="chronology").count(),
        "grammar": SubjectSectionEntry.objects.filter(subject=subject, section_key="grammar").count(),
        "rules": SubjectSectionEntry.objects.filter(subject=subject, section_key="rules").count(),
        "essay": essay_queryset.count(),
        "extras": SubjectSectionEntry.objects.filter(subject=subject, section_key="extras").count(),
        "ai": 0,
        "chat": 0,
    }
    section_previews = {
        "books": books[0].title if books else "",
        "tests": tests[0].title if tests else "",
        "formulas": SubjectSectionEntry.objects.filter(subject=subject, section_key="formulas")
        .order_by("created_at", "id")
        .values_list("title", flat=True)
        .first()
        or "",
        "formula-quiz": math_formula_quiz[0]["answer_title"] if math_formula_quiz else "",
        "problems": practice_sets[0].title if practice_sets else (tests[0].title if tests else ""),
        "mistakes": math_mistake_items[0]["title"] if math_mistake_items else "",
        "terms": SubjectSectionEntry.objects.filter(subject=subject, section_key="terms")
        .order_by("created_at", "id")
        .values_list("title", flat=True)
        .first()
        or "",
        "events": SubjectSectionEntry.objects.filter(subject=subject, section_key="events")
        .order_by("created_at", "id")
        .values_list("title", flat=True)
        .first()
        or "",
        "chronology": SubjectSectionEntry.objects.filter(subject=subject, section_key="chronology")
        .order_by("created_at", "id")
        .values_list("title", flat=True)
        .first()
        or "",
        "grammar": SubjectSectionEntry.objects.filter(subject=subject, section_key="grammar")
        .order_by("created_at", "id")
        .values_list("title", flat=True)
        .first()
        or "",
        "rules": SubjectSectionEntry.objects.filter(subject=subject, section_key="rules")
        .order_by("created_at", "id")
        .values_list("title", flat=True)
        .first()
        or "",
        "essay": essay_queryset.values_list("title", flat=True).first() or "",
        "extras": SubjectSectionEntry.objects.filter(subject=subject, section_key="extras")
        .order_by("created_at", "id")
        .values_list("title", flat=True)
        .first()
        or "",
        "ai": "",
        "chat": "",
    }
    workspace_focus = _build_workspace_focus(subject_theme["key"], section_totals)
    workspace_flow_steps = _build_workspace_flow_steps(subject_theme["key"])
    workspace_module_cards = _build_workspace_module_cards(
        section_items,
        section_catalog,
        section_totals,
        section_previews,
        workspace_focus["key"],
    )
    workspace_focus["status"] = (
        f"{workspace_focus['count']} ta ochiq blok"
        if workspace_focus["count"]
        else "Kontent kutilmoqda"
    )
    workspace_focus["preview"] = section_previews.get(workspace_focus["key"], "")
    workspace_focus["cta"] = section_catalog.get(workspace_focus["key"], {}).get("cta", "Ochish")
    current_section_label = next(
        (item["label"] for item in section_items if item["key"] == current_section),
        "Bo'lim",
    )

    context = {
        "profile": profile,
        "level_info": level_info,
        "subject_level": subject_level,
        "subject": subject,
        "peer_subjects": peer_subjects,
        "current_section": current_section,
        "section_items": section_items,
        "books": books,
        "tests": tests,
        "practice_sets": practice_sets,
        "subject_theme": subject_theme,
        "is_math_subject": is_math_subject,
        "home_metrics": home_metrics,
        "section_entries": section_entries,
        "current_section_label": current_section_label,
        "essay_topics": essay_topics,
        "selected_essay_progress": selected_essay_progress,
        "selected_essay_topic": selected_essay_topic,
        "essay_page_obj": essay_page_obj,
        "essay_highlights": essay_highlights,
        "essay_writing_steps": essay_writing_steps,
        "essay_exam_rules": essay_exam_rules,
        "essay_review_focus": essay_review_focus,
        "essay_self_check_cards": essay_self_check_cards,
        "essay_self_check_note": essay_self_check_note,
        "current_path": request.get_full_path(),
        "formula_entries": formula_entries,
        "formula_query": formula_query,
        "formula_filter": formula_filter,
        "selected_formula": selected_formula,
        "math_formula_quiz": math_formula_quiz,
        "math_mistake_items": math_mistake_items,
        "selected_history_entry": selected_history_entry,
        "selected_reference_entry": selected_reference_entry,
        "reference_page_obj": reference_page_obj,
        "reference_entries": reference_entries,
        "chronology_cards": chronology_cards,
        "selected_grammar_entry": selected_grammar_entry,
        "grammar_featured_count": grammar_featured_count,
        "grammar_total_count": grammar_total_count,
        "grammar_completed_count": grammar_completed_count,
        "grammar_progress_percent": grammar_progress_percent,
        "grammar_groups": grammar_groups,
        "grammar_lesson_rows": grammar_lesson_rows,
        "grammar_progress": grammar_progress,
        "grammar_questions": grammar_questions,
        "grammar_question_total": grammar_question_total,
        "grammar_quiz_result": grammar_quiz_result,
        "grammar_points": grammar_points,
        "grammar_selected_level": grammar_selected_level,
        "history_query": history_query,
        "history_page_obj": history_page_obj,
        "selected_grade": selected_grade,
        "grade_filters": grade_filters,
        "book_filter_title": book_filter_config["title"],
        "selected_test_filter": selected_test_filter,
        "history_test_filters": history_test_filters,
        "selected_problem_filter": selected_problem_filter,
        "language_problem_filters": language_problem_filters,
        "show_language_problem_filters": is_language_subject(subject),
        "combined_problem_items": combined_problem_items,
        "workspace_focus": workspace_focus,
        "workspace_flow_steps": workspace_flow_steps,
        "workspace_module_cards": workspace_module_cards,
        "workspace_available_modules": sum(
            1
            for item in section_items
            if item["key"] not in {"home", "ai", "chat"} and section_totals.get(item["key"], 0)
        ),
        "workspace_ready_resources": total_books_count + combined_problem_count,
        "xp_summary": xp_summary,
    }
    return render(request, "subject_workspace.html", context)


@login_required
def chronology_detail_view(request, subject_id, entry_id):
    profile = _get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    subject = get_object_or_404(Subject, id=subject_id)

    if not _user_can_access_subject(request.user, subject.id):
        messages.error(request, "Bu fan siz uchun hali aktiv emas.")
        return redirect("subject-selection")

    entry_queryset = SubjectSectionEntry.objects.filter(subject=subject, section_key="chronology")
    entries = list(entry_queryset)
    entry = get_object_or_404(entry_queryset, id=entry_id)
    entry_index = next((index for index, item in enumerate(entries) if item.id == entry.id), 0)
    previous_entry = entries[entry_index - 1] if entry_index > 0 else None
    next_entry = entries[entry_index + 1] if entry_index < len(entries) - 1 else None

    return render(
        request,
        "history_chronology_detail.html",
        {
            **_sidebar_context(request.user),
            "subject": subject,
            "entry": entry,
            "chronology_lines": _split_chronology_lines(entry),
            "previous_entry": previous_entry,
            "next_entry": next_entry,
            "level_info": level_info,
            "profile": profile,
            "current_path": request.get_full_path(),
        },
    )


@login_required
def profile_view(request):
    profile = _get_or_sync_profile(request.user)
    xp_summary = _get_user_progress_summary(request.user)
    level_info = get_level_info(profile.xp)
    profile_summary = get_user_profile_summary(request.user, level_info["label"])
    premium_is_active = bool(profile.premium_until and profile.premium_until >= timezone.now())
    context = {
        "profile": profile,
        "profile_photo_url": _get_safe_profile_photo_url(profile),
        "level_info": level_info,
        "subject_statuses": profile_summary["subject_statuses"],
        "rank_position": profile_summary["rank_position"],
        "total_tests": profile_summary["total_tests"],
        "purchased_subject_names": profile_summary["purchased_subject_names"],
        "active_subject_count": profile_summary["active_subject_count"],
        "member_since": profile.created_at,
        "xp_summary": xp_summary,
        "premium_is_active": premium_is_active,
    }
    return render(request, "profile_refined.html", context)


@login_required
def subject_selection_view(request):
    sidebar = _sidebar_context(request.user)
    access_rows = _get_user_subject_access_rows(request.user, active_only=True)
    subscribed_subject_ids = {row["subject_id"] for row in access_rows}
    access_map = {row["subject_id"]: row for row in access_rows}
    purchase_contact_url = "https://t.me/umarovv_2"
    referral_summary = _get_referral_summary(request.user)
    referral_summary["share_url"] = request.build_absolute_uri(
        reverse("referral-entry", args=[referral_summary["referral_code"]])
    )
    plan_catalog = _ensure_default_subscription_plans()
    subjects = list(Subject.objects.all().order_by("name"))
    subject_ids = [subject.id for subject in subjects]

    test_counts = {
        row["subject_id"]: row["count"]
        for row in Test.objects.filter(subject_id__in=subject_ids)
        .values("subject_id")
        .annotate(count=Count("id"))
    }
    book_counts = {
        row["subject_id"]: row["count"]
        for row in Book.objects.filter(subject_id__in=subject_ids)
        .values("subject_id")
        .annotate(count=Count("id"))
    }
    practice_counts = {
        row["subject_id"]: row["count"]
        for row in PracticeSet.objects.filter(subject_id__in=subject_ids)
        .values("subject_id")
        .annotate(count=Count("id"))
    }
    section_counts = {
        row["subject_id"]: row["count"]
        for row in SubjectSectionEntry.objects.filter(subject_id__in=subject_ids)
        .values("subject_id")
        .annotate(count=Count("id"))
    }
    essay_counts = {
        row["subject_id"]: row["count"]
        for row in EssayTopic.objects.filter(subject_id__in=subject_ids)
        .values("subject_id")
        .annotate(count=Count("id"))
    }

    subject_cards = []
    for subject in subjects:
        access_row = access_map.get(subject.id)
        subject_cards.append(
            {
                "id": subject.id,
                "name": subject.name,
                "price": subject.price,
                "material_count": (
                    test_counts.get(subject.id, 0)
                    + book_counts.get(subject.id, 0)
                    + practice_counts.get(subject.id, 0)
                    + section_counts.get(subject.id, 0)
                    + essay_counts.get(subject.id, 0)
                ),
                "is_active": subject.id in subscribed_subject_ids,
                "status_label": "Faol" if subject.id in subscribed_subject_ids else "Mavjud",
                "source_label": (
                    "Free fan"
                    if access_row and access_row["source"] == "free"
                    else "Bundle"
                    if access_row and access_row["source"] == "bundle"
                    else "Fan obunasi"
                ),
                "end_at": access_row["end_at"] if access_row else None,
            }
        )

    active_subject_cards = [card for card in subject_cards if card["is_active"]]
    locked_subject_cards = [card for card in subject_cards if not card["is_active"]]
    available_count = len(subject_cards)
    active_count = len(active_subject_cards)

    has_paid_access = active_count > 0
    plan_cards = [
        {
            "code": "free",
            "catalog_code": "free",
            "name": "FREE",
            "label": "Boshlang'ich",
            "theme": "free",
            "price_label": "0 so'm",
            "coverage_label": "1 ta fan",
            "status_text": "1 ta fan tanlanadi",
            "description": "Boshlash uchun bepul reja.",
            "features": [
                "1 ta fan ochiladi",
                "Kuniga 3 ta mashq",
                "Basic statistika",
                "AI kuniga 2-3 marta",
                "O'yinlar",
            ],
            "limits": [
                "Boshqa fanlar yopiq",
                "To'liq AI analiz yo'q",
                "Advanced content yopiq",
            ],
            "note": "",
            "is_featured": False,
            "is_current": not has_paid_access,
            "cta_label": "Default reja",
            "cta_href": "",
            "cta_external": False,
        },
        {
            "code": "single-subject",
            "catalog_code": "single-subject",
            "name": "SINGLE SUBJECT",
            "label": "1 ta qo'shimcha fan",
            "theme": "single",
            "price_label": "30,000 so'm",
            "coverage_label": "Free + 1",
            "status_text": "1 ta qo'shimcha fan ochiladi",
            "description": "1 ta qo'shimcha fan kerak bo'lganlar uchun qulay reja.",
            "features": [
                "1 ta qo'shimcha fan ochiladi",
                "Cheksiz mashqlar",
                "To'liq content",
                "AI o'rtacha darajada",
            ],
            "limits": [],
            "note": "",
            "is_featured": False,
            "is_current": False,
            "cta_label": "Sotib olish",
            "cta_href": purchase_contact_url,
            "cta_external": True,
        },
        {
            "code": "pro",
            "catalog_code": "triple-subject",
            "name": "PRO",
            "label": "Eng ko'p sotiladigan",
            "theme": "pro",
            "price_label": "70,000 so'm",
            "coverage_label": "3 ta fan",
            "status_text": "3 ta fan ochiladi",
            "description": "Ko'pchilik uchun asosiy paket: keng content, kuchli AI va progress tracking.",
            "features": [
                "3 ta fan ochiladi",
                "Cheksiz mashqlar",
                "To'liq content",
                "AI analiz to'liqroq",
                "Progress tracking va tavsiyalar",
            ],
            "limits": [],
            "note": "",
            "is_featured": True,
            "is_current": False,
            "cta_label": "Sotib olish",
            "cta_href": purchase_contact_url,
            "cta_external": True,
        },
        {
            "code": "premium",
            "catalog_code": "all-access",
            "name": "PREMIUM",
            "label": "Top reja",
            "theme": "premium",
            "price_label": "100,000 - 120,000 so'm",
            "coverage_label": "Barcha fanlar",
            "status_text": "Barcha fanlar ochiq",
            "description": "Barcha fanlar, mock exam, to'liq AI analiz va advanced statistika bitta rejada.",
            "features": [
                "Barcha fanlar ochiq",
                "Cheksiz mashqlar va mock exam",
                "AI to'liq analiz",
                "Reyting, XP va advanced statistika",
                "Yangi materiallarga early access",
            ],
            "limits": [],
            "note": "",
            "is_featured": True,
            "is_current": available_count > 0 and active_count >= available_count,
            "cta_label": "Sotib olish",
            "cta_href": purchase_contact_url,
            "cta_external": True,
        },
    ]

    for plan in plan_cards:
        catalog_plan = plan_catalog.get(plan.get("catalog_code") or plan["code"])
        quote = _get_referral_plan_quote(catalog_plan, referral_summary["available_percent"]) if catalog_plan else {
            "eligible": False,
            "base_price": 0,
            "discount_percent": 0,
            "discount_amount": 0,
            "final_price": 0,
        }
        if catalog_plan and quote["base_price"] and plan["code"] != "premium":
            plan["price_label"] = _format_price_label(quote["base_price"])
        elif catalog_plan and quote["base_price"] and plan["code"] == "premium":
            plan["price_label"] = _format_price_label(quote["base_price"])
        plan["referral_discount_percent"] = quote["discount_percent"]
        plan["referral_final_price_label"] = _format_price_label(quote["final_price"]) if quote["discount_percent"] else ""
        plan["referral_note"] = (
            f"Taklif chegirmasi bilan keyingi xarid {plan['referral_final_price_label']} bo'ladi."
            if quote["discount_percent"]
            else ""
        )

    if active_count == 0:
        access_title = "Obuna tanlanmagan"
        access_hint = "Kerakli rejani tanlab, fanlarni ochishingiz mumkin."
    elif active_count >= available_count and available_count > 0:
        access_title = "Barcha fanlar ochiq"
        access_hint = "Sizda barcha fanlar uchun kirish mavjud."
    else:
        access_title = f"{active_count} ta fan ochiq"
        access_hint = "Qo'shimcha fanlarni xohlagan payt ochishingiz mumkin."

    context = {
        **sidebar,
        "subject_cards": subject_cards,
        "active_subject_cards": active_subject_cards,
        "locked_subject_cards": locked_subject_cards,
        "active_count": active_count,
        "available_count": available_count,
        "inactive_count": max(available_count - active_count, 0),
        "plan_cards": plan_cards,
        "access_title": access_title,
        "access_hint": access_hint,
        "purchase_contact_url": purchase_contact_url,
        "referral_summary": referral_summary,
        "current_subscription_notice": "Mavjud obunalar saqlanadi. Yangi xaridlar va qo'shimcha fan ochish hozircha Telegram orqali boshqariladi.",
    }
    return render(request, "subject_selection.html", context)


@login_required
def ranking_view(request):
    sidebar = _sidebar_context(request.user)
    subject_filter = request.GET.get("subject", "").strip()
    tests_filter = request.GET.get("tests", "all").strip()

    subject_queryset = Subject.objects.order_by("name")
    users = get_ranking_queryset(subject_filter, tests_filter)

    ranking_rows = []
    for index, user in enumerate(users, start=1):
        profile = getattr(user, "profile", None)
        display_name = profile.full_name if profile and profile.full_name else user.first_name or user.username
        role_label = profile.get_role_display() if profile else "O'quvchi"
        ranking_rows.append(
            {
                "rank": index,
                "name": display_name,
                "username": user.username,
                "best_score": user.best_score,
                "tests": user.total_tests,
                "level": getattr(profile, "level", "C") if profile else "C",
                "xp": user.effective_xp,
                "role": role_label,
                "initials": _build_user_initials(display_name, user.username),
                "photo_url": profile.photo.url if profile and profile.photo else "",
                "is_current_user": user.id == request.user.id,
            }
        )

    current_user_row = next((row for row in ranking_rows if row["is_current_user"]), None)
    podium_source = ranking_rows[:3]
    podium_rows = []
    if len(podium_source) > 1:
        podium_rows.append(
            {
                **podium_source[1],
                "visual_rank": 2,
                "accent": "silver",
                "slot": "left",
            }
        )
    if len(podium_source) > 0:
        podium_rows.append(
            {
                **podium_source[0],
                "visual_rank": 1,
                "accent": "gold",
                "slot": "center",
            }
        )
    if len(podium_source) > 2:
        podium_rows.append(
            {
                **podium_source[2],
                "visual_rank": 3,
                "accent": "bronze",
                "slot": "right",
            }
        )

    return render(
        request,
        "ranking.html",
        {
            **sidebar,
            "ranking_rows": ranking_rows,
            "current_user_row": current_user_row,
            "podium_rows": podium_rows,
            "remaining_rows": ranking_rows[3:],
            "ranking_subjects": subject_queryset,
            "selected_subject": subject_filter,
            "selected_tests_filter": tests_filter,
        },
    )


@login_required
def statistics_view(request):
    sidebar = _sidebar_context(request.user)
    stats_payload = get_statistics_payload(
        request.user,
        sidebar["profile"].xp,
        sidebar["level_info"]["label"],
    )

    context = {
        **sidebar,
        "stats": stats_payload["stats"],
        "subject_rows": stats_payload["subject_rows"],
        "recent_attempts": stats_payload["recent_attempts"],
    }
    return render(request, "statistics.html", context)
