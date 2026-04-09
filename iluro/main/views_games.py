from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from .selectors import (
    HISTORY_BATTLE_QUESTION_TARGET,
    get_history_battle_questions,
    get_history_game_grade_options,
)
from .services import get_or_sync_profile, get_user_progress_summary
from .utils import get_level_info


@login_required
def games_hub_view(request):
    profile = get_or_sync_profile(request.user)
    level_info = get_level_info(profile.xp)
    xp_summary = get_user_progress_summary(request.user)
    grade_options = get_history_game_grade_options()

    games = [
        {
            "title": "Tarix jangi",
            "slug": "history-battle",
            "description": "Sinf bo'yicha tarix savollaridan yig'ilgan duel o'yini. Har safar mavjud saytdagi savollardan yangi deck tuziladi.",
            "status": "Faol",
            "meta": f"{len(grade_options)} ta sinf mavjud" if grade_options else "Savollar kutilmoqda",
            "href": "history-battle",
        },
        {
            "title": "Tez orada",
            "slug": "coming-soon",
            "description": "Keyingi bosqichda boshqa fanlar uchun ham qisqa battle va memory formatlari ulanadi.",
            "status": "Coming soon",
            "meta": "Yangi o'yinlar kutilmoqda",
            "href": "",
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
