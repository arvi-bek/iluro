from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .models import (
    EssayTopic,
    GRADE_CHOICES,
    Subject,
    SubjectSectionEntry,
)
from .selectors import (
    get_dashboard_subject_cards,
    get_formula_entries,
    get_latest_dashboard_resources,
    get_ranking_queryset,
    get_statistics_payload,
    get_subject_books,
    get_subject_peer_subjects,
    get_subject_practice_sets,
    get_subject_tests,
    get_user_profile_summary,
    get_user_subject_best_score,
)
from .services import (
    filter_by_allowed_level as _filter_by_allowed_level,
    get_active_subscription_ids as _get_active_subscription_ids,
    get_or_sync_profile as _get_or_sync_profile,
    get_subject_theme as _get_subject_theme,
    sidebar_context as _sidebar_context,
    user_can_access_subject as _user_can_access_subject,
)
from .utils import get_level_info


@login_required
def dashboard_view(request):
    profile = _get_or_sync_profile(request.user)
    selected_subject_id = request.GET.get("subject")
    subjects = get_dashboard_subject_cards(request.user)
    for subject in subjects:
        subject["is_selected"] = str(subject["id"]) == str(selected_subject_id)

    latest_test, featured_book = get_latest_dashboard_resources()
    level_info = get_level_info(profile.xp)
    if profile.level != level_info["label"]:
        profile.level = level_info["label"]
        profile.save(update_fields=["level"])

    quick_actions = [
        "Fanlarni tekshirish va obunalarni ko'rish",
        "Testlar sahifasidan mashqni boshlash",
        "Kitoblar sahifasidan resurslarni ochish",
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
            "hint": "Faqat to'liq to'g'ri ishlangan test uchun 1 XP",
        },
    ]
    context = {
        "profile": profile,
        "stats": stats,
        "subjects": subjects,
        "hub_cards": hub_cards,
        "quick_actions": quick_actions,
        "level_info": level_info,
    }
    return render(request, "dashboard.html", context)


@login_required
def subject_workspace_view(request, subject_id, section=None):
    profile = _get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    subject = get_object_or_404(Subject.objects.annotate(test_count=Count("test")), id=subject_id)
    selected_grade = request.GET.get("grade", "").strip()
    allowed_grades = {choice[0] for choice in GRADE_CHOICES}

    if not _user_can_access_subject(request.user, subject.id):
        messages.error(request, "Bu fan uchun sizda aktiv obuna yo'q.")
        return redirect("subject-selection")

    current_section = section or request.GET.get("section", "home")
    subject_theme = _get_subject_theme(subject.name)
    allowed_sections = {"home", "books", "tests", "ai", "chat"} | {
        item["key"] for item in subject_theme["extra_sections"]
    }
    if current_section not in allowed_sections:
        current_section = "home"

    peer_subjects = get_subject_peer_subjects(request.user, subject.id)

    books = get_subject_books(subject, grade=selected_grade if selected_grade in allowed_grades else None, limit=12)
    grade_filters = [{"value": "", "label": "Barchasi", "is_active": selected_grade == ""}]
    grade_filters.extend(
        {
            "value": value,
            "label": label,
            "is_active": selected_grade == value,
        }
        for value, label in GRADE_CHOICES
    )
    tests = get_subject_tests(request.user, subject, profile.level, limit=6)
    practice_sets = get_subject_practice_sets(request.user, subject, profile.level, limit=12)

    section_items = [
        {"key": "home", "label": "Asosiy menyu"},
        {"key": "books", "label": "Kitoblar"},
        {"key": "tests", "label": "Mashqlar (Test)"},
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
    home_metrics = [
        {"label": "Joriy daraja", "value": level_info["label"], "hint": f"{profile.xp} XP bilan ochilgan umumiy daraja"},
        {"label": "Testlar", "value": subject.test_count, "hint": "Mavjud mashqlar soni"},
        {"label": "Eng yaxshi natija", "value": f"{user_subject_best}%", "hint": "Shu fan bo'yicha eng yaxshi foiz"},
    ]
    formula_query = (request.GET.get("q") or "").strip()
    formula_filter = request.GET.get("formula_filter", "all")
    formula_entries = get_formula_entries(subject, formula_query, formula_filter)

    section_entries = list(
        _filter_by_allowed_level(
            SubjectSectionEntry.objects.filter(subject=subject, section_key=current_section),
            "access_level",
            profile.level,
        )
    )
    essay_topics = list(
        _filter_by_allowed_level(EssayTopic.objects.filter(subject=subject), "access_level", profile.level)[:6]
    )
    current_section_label = next(
        (item["label"] for item in section_items if item["key"] == current_section),
        "Bo'lim",
    )

    context = {
        "profile": profile,
        "level_info": level_info,
        "subject": subject,
        "peer_subjects": peer_subjects,
        "current_section": current_section,
        "section_items": section_items,
        "books": books,
        "tests": tests,
        "practice_sets": practice_sets,
        "subject_theme": subject_theme,
        "home_metrics": home_metrics,
        "section_entries": section_entries,
        "current_section_label": current_section_label,
        "essay_topics": essay_topics,
        "current_path": request.get_full_path(),
        "formula_entries": formula_entries,
        "formula_query": formula_query,
        "formula_filter": formula_filter,
        "selected_grade": selected_grade,
        "grade_filters": grade_filters,
    }
    return render(request, "subject_workspace.html", context)


@login_required
def profile_view(request):
    profile = _get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    profile_summary = get_user_profile_summary(request.user, level_info["label"])
    context = {
        "profile": profile,
        "level_info": level_info,
        "subject_statuses": profile_summary["subject_statuses"],
        "rank_position": profile_summary["rank_position"],
        "total_tests": profile_summary["total_tests"],
        "purchased_subject_names": profile_summary["purchased_subject_names"],
        "active_subject_count": profile_summary["active_subject_count"],
        "member_since": profile.created_at,
    }
    return render(request, "profile.html", context)


@login_required
def subject_selection_view(request):
    sidebar = _sidebar_context(request.user)
    subscribed_subject_ids = set(_get_active_subscription_ids(request.user))
    subjects = Subject.objects.all().annotate(test_count=Count("test")).order_by("name")

    subject_cards = [
        {
            "id": subject.id,
            "name": subject.name,
            "price": subject.price,
            "test_count": subject.test_count,
            "is_active": subject.id in subscribed_subject_ids,
        }
        for subject in subjects
    ]

    context = {
        **sidebar,
        "subject_cards": subject_cards,
        "active_count": len(subscribed_subject_ids),
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
        ranking_rows.append(
            {
                "rank": index,
                "name": display_name,
                "username": user.username,
                "best_score": user.best_score,
                "tests": user.total_tests,
                "level": getattr(profile, "level", "S") if profile else "S",
                "xp": user.effective_xp,
            }
        )

    return render(
        request,
        "ranking.html",
        {
            **sidebar,
            "ranking_rows": ranking_rows,
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
