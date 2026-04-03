from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import (
    EssayTopic,
    GRADE_CHOICES,
    GrammarLessonProgress,
    GrammarLessonQuestion,
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
    get_effective_subject_level as _get_effective_subject_level,
    get_or_sync_profile as _get_or_sync_profile,
    get_subject_theme as _get_subject_theme,
    get_user_progress_summary as _get_user_progress_summary,
    sidebar_context as _sidebar_context,
    user_can_access_subject as _user_can_access_subject,
)
from .utils import LEVEL_ORDER, get_allowed_level_labels, get_level_info


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


@login_required
def dashboard_view(request):
    profile = _get_or_sync_profile(request.user)
    xp_summary = _get_user_progress_summary(request.user)
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
            "hint": "Daraja yig'ilgan XP orqali o'sadi.",
        },
    ]
    context = {
        "profile": profile,
        "stats": stats,
        "subjects": subjects,
        "hub_cards": hub_cards,
        "quick_actions": quick_actions,
        "level_info": level_info,
        "xp_summary": xp_summary,
        "show_beta_trial_notice": bool(request.session.get("beta_trial_notice")),
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
        raise Http404("Bunday bo'lim mavjud emas.")

    peer_subjects = get_subject_peer_subjects(request.user, subject.id)

    selected_book_grade = selected_grade if selected_grade in allowed_grades or selected_grade == "other" else None
    books = get_subject_books(subject, grade=selected_book_grade, limit=12)
    grade_filters = [{"value": "", "label": "Barchasi", "is_active": selected_grade == ""}]
    grade_filters.extend(
        {
            "value": value,
            "label": label,
            "is_active": selected_grade == value,
        }
        for value, label in GRADE_CHOICES
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
    tests = get_subject_tests(
        request.user,
        subject,
        subject_level,
        limit=6,
        category_filter=selected_test_filter,
    )
    history_test_filters = [
        {"value": "all", "label": "Umumiy", "is_active": selected_test_filter == "all"},
        {"value": "terms", "label": "Atamalar bo'yicha", "is_active": selected_test_filter == "terms"},
        {"value": "years", "label": "Yillar bo'yicha", "is_active": selected_test_filter == "years"},
    ]
    practice_sets = get_subject_practice_sets(request.user, subject, subject_level, limit=12)

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
        {"label": "Joriy daraja", "value": subject_level, "hint": "Shu fan uchun tanlangan joriy daraja"},
        {"label": "Testlar", "value": subject.test_count, "hint": "Mavjud mashqlar soni"},
        {"label": "Eng yaxshi natija", "value": f"{user_subject_best}%", "hint": "Shu fan bo'yicha eng yaxshi foiz"},
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

    history_query = (request.GET.get("q") or "").strip()
    history_page_obj = None
    grammar_progress_map = {}
    grammar_lesson_rows = []
    grammar_questions = []
    grammar_question_total = 0
    grammar_progress = None
    grammar_quiz_result = None
    grammar_selected_level = subject_level
    grammar_allowed_levels = get_allowed_level_labels(subject_level)

    base_section_entries_queryset = SubjectSectionEntry.objects.filter(subject=subject, section_key=current_section)
    if current_section == "grammar":
        section_entries_queryset = base_section_entries_queryset
    else:
        section_entries_queryset = _filter_by_allowed_level(
            base_section_entries_queryset,
            "access_level",
            subject_level,
        )
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
    if current_section == "grammar" and section_entries:
        requested_grammar_level = (request.GET.get("grammar_level") or "").strip().replace(" ", "+")
        available_grammar_levels = [
            level
            for level in grammar_allowed_levels
            if any(entry.access_level == level for entry in section_entries)
        ]
        if available_grammar_levels:
            if requested_grammar_level in available_grammar_levels:
                grammar_selected_level = requested_grammar_level
            elif subject_level in available_grammar_levels:
                grammar_selected_level = subject_level
            else:
                grammar_selected_level = available_grammar_levels[0]

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
            grammar_progress.last_score = score
            grammar_progress.best_score = max(grammar_progress.best_score, score)
            grammar_progress.attempts_count += 1
            if passed and not grammar_progress.is_completed:
                grammar_progress.is_completed = True
                grammar_progress.completed_at = timezone.now()
            grammar_progress.save()

            grammar_progress_map[selected_grammar_entry.id] = grammar_progress
            grammar_lesson_rows = _build_grammar_lesson_rows(filtered_grammar_entries, grammar_progress_map)
            grammar_quiz_result = {
                "score": score,
                "correct_count": correct_count,
                "total_questions": total_questions,
                "passed": passed,
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
        grammar_allowed_levels,
        grammar_selected_level,
    ) if current_section == "grammar" else []
    grammar_points = _build_grammar_points(selected_grammar_entry) if current_section == "grammar" else []
    essay_topics = list(
        _filter_by_allowed_level(EssayTopic.objects.filter(subject=subject), "access_level", subject_level)[:6]
    )
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
        "home_metrics": home_metrics,
        "section_entries": section_entries,
        "current_section_label": current_section_label,
        "essay_topics": essay_topics,
        "current_path": request.get_full_path(),
        "formula_entries": formula_entries,
        "formula_query": formula_query,
        "formula_filter": formula_filter,
        "selected_formula": selected_formula,
        "selected_history_entry": selected_history_entry,
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
        "selected_test_filter": selected_test_filter,
        "history_test_filters": history_test_filters,
        "xp_summary": xp_summary,
    }
    return render(request, "subject_workspace.html", context)


@login_required
def chronology_detail_view(request, subject_id, entry_id):
    profile = _get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    subject = get_object_or_404(Subject, id=subject_id)
    subject_level = _get_effective_subject_level(request.user, subject_id=subject.id, profile=profile)

    if not _user_can_access_subject(request.user, subject.id):
        messages.error(request, "Bu fan siz uchun hali aktiv emas.")
        return redirect("subject-selection")

    entry_queryset = _filter_by_allowed_level(
        SubjectSectionEntry.objects.filter(subject=subject, section_key="chronology"),
        "access_level",
        subject_level,
    )
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
    context = {
        "profile": profile,
        "level_info": level_info,
        "subject_statuses": profile_summary["subject_statuses"],
        "rank_position": profile_summary["rank_position"],
        "total_tests": profile_summary["total_tests"],
        "purchased_subject_names": profile_summary["purchased_subject_names"],
        "active_subject_count": profile_summary["active_subject_count"],
        "member_since": profile.created_at,
        "xp_summary": xp_summary,
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
