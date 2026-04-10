from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from .selectors import (
    HISTORY_BATTLE_QUESTION_TARGET,
    IMLO_DUEL_QUESTION_TARGET,
    get_history_battle_questions,
    get_history_game_grade_options,
    get_language_duel_subject_options,
    get_imlo_duel_grade_options,
    get_imlo_duel_questions,
)
from .services import get_or_sync_profile, get_user_progress_summary
from .utils import get_level_info


@login_required
def games_hub_view(request):
    profile = get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    xp_summary = get_user_progress_summary(request.user)
    grade_options = get_history_game_grade_options()
    imlo_options = get_imlo_duel_grade_options("language")

    games = [
        {
            "title": "Qal'a o'yini",
            "slug": "history-battle",
            "description": "Sinf bo'yicha tarix savollaridan yig'ilgan duel o'yini. Har safar mavjud saytdagi savollardan yangi deck tuziladi.",
            "status": "Faol",
            "meta": f"{len(grade_options)} ta sinf mavjud" if grade_options else "Savollar kutilmoqda",
            "href": "history-battle",
        },
        {
            "title": "Imlo dueli",
            "slug": "imlo-duel",
            "description": "Ona tili va adabiyot savollarini fan hamda sinf bo'yicha duel formatida takrorlash uchun o'yin.",
            "status": "Faol",
            "meta": f"{len(imlo_options)} ta sinf mavjud" if imlo_options else "Savollar kutilmoqda",
            "href": "imlo-duel",
        },
    ]

    return render(
        request,
        "games_hub.html",
        {
            "profile": profile,
            "level_info": level_info,
            "xp_summary": xp_summary,
            "games": games,
            "grade_options": grade_options,
            "imlo_options": imlo_options,
        },
    )


@login_required
def history_battle_view(request):
    profile = get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    xp_summary = get_user_progress_summary(request.user)
    grade_options = get_history_game_grade_options()
    screen_mode = "board" if request.GET.get("screen") == "board" else "default"
    selected_grade = request.GET.get("grade", "").strip()
    if selected_grade and not any(item["value"] == selected_grade for item in grade_options):
        selected_grade = ""
    if not selected_grade and grade_options:
        selected_grade = grade_options[0]["value"]

    selected_option = next((item for item in grade_options if item["value"] == selected_grade), None)
    preview_questions = get_history_battle_questions(selected_grade, limit=1) if selected_grade else []

    return render(
        request,
        "history_battle_full.html",
        {
            "profile": profile,
            "level_info": level_info,
            "xp_summary": xp_summary,
            "grade_options": grade_options,
            "selected_grade": selected_grade,
            "selected_option": selected_option,
            "preview_question": preview_questions[0] if preview_questions else None,
            "screen_mode": screen_mode,
        },
    )


@login_required
def history_battle_questions_view(request):
    selected_grade = request.GET.get("grade", "").strip()
    try:
        requested_limit = int(request.GET.get("limit") or HISTORY_BATTLE_QUESTION_TARGET)
    except (TypeError, ValueError):
        requested_limit = HISTORY_BATTLE_QUESTION_TARGET
    requested_limit = max(2, min(requested_limit, 60))

    deck = get_history_battle_questions(selected_grade, limit=requested_limit)
    grade_options = get_history_game_grade_options()
    selected_option = next((item for item in grade_options if item["value"] == selected_grade), None)

    if not deck:
        return JsonResponse(
            {
                "ok": False,
                "message": "Tanlangan sinf bo'yicha yetarli tarix savollari topilmadi.",
            },
            status=404,
        )

    return JsonResponse(
        {
            "ok": True,
            "grade": selected_grade,
            "grade_label": selected_option["label"] if selected_option else "Tarix",
            "question_count": len(deck),
            "questions": deck,
        }
    )


@login_required
def imlo_duel_view(request):
    profile = get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    xp_summary = get_user_progress_summary(request.user)
    subject_options = get_language_duel_subject_options()
    selected_subject = request.GET.get("subject", "").strip() or "language"
    if selected_subject not in {item["value"] for item in subject_options}:
        selected_subject = "language"
    grade_options_map = {
        item["value"]: get_imlo_duel_grade_options(item["value"])
        for item in subject_options
    }
    level_options = grade_options_map.get(selected_subject, [])
    screen_mode = "board" if request.GET.get("screen") == "board" else "default"
    selected_level = request.GET.get("grade", "").strip()
    if selected_level and not any(item["value"] == selected_level for item in level_options):
        selected_level = ""
    if not selected_level and level_options:
        selected_level = level_options[0]["value"]

    selected_subject_option = next((item for item in subject_options if item["value"] == selected_subject), None)
    selected_option = next((item for item in level_options if item["value"] == selected_level), None)
    preview_questions = (
        get_imlo_duel_questions(selected_level, limit=1, subject_kind=selected_subject)
        if selected_level else []
    )

    return render(
        request,
        "imlo_duel_full.html",
        {
            "profile": profile,
            "level_info": level_info,
            "xp_summary": xp_summary,
            "subject_options": subject_options,
            "grade_options_map": grade_options_map,
            "selected_subject": selected_subject,
            "selected_subject_option": selected_subject_option,
            "grade_options": level_options,
            "selected_grade": selected_level,
            "selected_option": selected_option,
            "preview_question": preview_questions[0] if preview_questions else None,
            "screen_mode": screen_mode,
        },
    )


@login_required
def imlo_duel_questions_view(request):
    selected_subject = request.GET.get("subject", "").strip() or "language"
    subject_options = get_language_duel_subject_options()
    if selected_subject not in {item["value"] for item in subject_options}:
        selected_subject = "language"
    selected_level = request.GET.get("grade", "").strip()
    try:
        requested_limit = int(request.GET.get("limit") or IMLO_DUEL_QUESTION_TARGET)
    except (TypeError, ValueError):
        requested_limit = IMLO_DUEL_QUESTION_TARGET
    requested_limit = max(2, min(requested_limit, 60))

    deck = get_imlo_duel_questions(selected_level, limit=requested_limit, subject_kind=selected_subject)
    level_options = get_imlo_duel_grade_options(selected_subject)
    selected_subject_option = next((item for item in subject_options if item["value"] == selected_subject), None)
    selected_option = next((item for item in level_options if item["value"] == selected_level), None)

    if not deck:
        return JsonResponse(
            {
                "ok": False,
                "message": f"Tanlangan fan va sinf bo'yicha yetarli savol topilmadi.",
            },
            status=404,
        )

    return JsonResponse(
        {
            "ok": True,
            "subject": selected_subject,
            "subject_label": selected_subject_option["label"] if selected_subject_option else "Ona tili",
            "grade": selected_level,
            "grade_label": selected_option["label"] if selected_option else "Aralash",
            "question_count": len(deck),
            "questions": deck,
        }
    )
