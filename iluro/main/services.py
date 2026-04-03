from django.contrib.auth.models import User
from django.db.models import Max
from django.utils import timezone

from .models import (
    Profile,
    Subscription,
    UserSubjectPreference,
    UserPracticeAttempt,
    UserTest,
)
from .utils import (
    XP_PER_CORRECT_PRACTICE_ANSWER,
    XP_PER_CORRECT_TEST_ANSWER,
    get_allowed_level_labels,
    get_level_info,
    normalize_difficulty_label,
)


def get_subject_theme(subject_name):
    subject_name_lower = subject_name.lower()

    if "matem" in subject_name_lower:
        return {
            "key": "math",
            "eyebrow": "Mantiq va tezlik",
            "headline": "Formula, masala va ritm bilan ishlaydigan aniq workspace.",
            "description": "Matematika bo'limida tezkor mashqlar, formulalarni mustahkamlash va natijani bosqichma-bosqich oshirish asosiy fokus bo'ladi.",
            "stat_label": "Masala ritmi",
            "stat_value": "Tezkor",
            "cards": [
                {"title": "Bugungi fokus", "text": "Masalani turlarga ajratish, formulani eslash va vaqtni yutish."},
                {"title": "Mashq usuli", "text": "Qisqa bloklarda test ishlab, natijani keyinroq tahlil qilish."},
                {"title": "AI yo'nalishi", "text": "Yechim bosqichlarini sodda tilda tushuntirish va xatoni topish."},
            ],
            "extra_sections": [
                {"key": "formulas", "label": "Formulalar"},
                {"key": "problems", "label": "Misol / Masalalar"},
            ],
        }

    if "tarix" in subject_name_lower:
        return {
            "key": "history",
            "eyebrow": "Davr va tafsilot",
            "headline": "Sanalar, jarayonlar va tarixiy bog'lanishlarni ushlab turadigan workspace.",
            "description": "Tarix bo'limida mavzularni davrlar bo'yicha ajratish, jarayonlarni taqqoslash va testlarda xotirani mustahkamlash markazga chiqadi.",
            "stat_label": "Tarixiy oqim",
            "stat_value": "Davrlar",
            "cards": [
                {"title": "Bugungi fokus", "text": "Davrlar orasidagi bog'lanishni ko'rish va sanalarni joyiga qo'yish."},
                {"title": "Mashq usuli", "text": "Mavzu bo'yicha test ishlashdan oldin qisqa kontsept xarita tuzish."},
                {"title": "AI yo'nalishi", "text": "Voqealar ketma-ketligini soddalashtirib tushuntirish va solishtirish."},
            ],
            "extra_sections": [
                {"key": "chronology", "label": "Xronologiya"},
                {"key": "terms", "label": "Atamalar"},
                {"key": "events", "label": "Sanalar / Voqealar"},
            ],
        }

    return {
        "key": "language",
        "eyebrow": "Matn va insho",
        "headline": "Grammatika, tahlil va insho ustida ishlashga mos ijodiy workspace.",
        "description": "Ona tili va adabiyot bo'limida matn bilan ishlash, grammatik tozalikni oshirish va insho strukturasini kuchaytirish asosiy yo'nalish bo'ladi.",
        "stat_label": "Matn rejimi",
        "stat_value": "Insho",
        "cards": [
            {"title": "Bugungi fokus", "text": "Matnni to'g'ri qurish, uslubni silliqlash va fikrni ravshan berish."},
            {"title": "Mashq usuli", "text": "Grammatika testlari va insho rejasini parallel ishlatish."},
            {"title": "AI yo'nalishi", "text": "Insho uchun reja, xato tahlili va jumla takomillashtirish."},
        ],
        "extra_sections": [
            {"key": "grammar", "label": "Gramatika"},
            {"key": "rules", "label": "Qoidalar"},
            {"key": "essay", "label": "Insho"},
            {"key": "extras", "label": "Qo'shimcha ma'lumotlar"},
        ],
    }


def get_active_subscription_ids(user):
    now = timezone.now()
    latest_subject_subscriptions = (
        Subscription.objects.filter(user=user)
        .values("subject_id")
        .annotate(latest_end_date=Max("end_date"))
    )
    return [
        item["subject_id"]
        for item in latest_subject_subscriptions
        if item["latest_end_date"] and item["latest_end_date"] >= now
    ]


def user_can_access_subject(user, subject_id):
    active_ids = get_active_subscription_ids(user)
    return subject_id in active_ids


def get_or_sync_profile(user: User):
    profile, _ = Profile.objects.get_or_create(
        user=user,
        defaults={
            "full_name": user.first_name or user.username,
        },
    )
    if user.is_superuser and profile.role != "admin":
        profile.role = "admin"
        profile.save(update_fields=["role"])
    elif user.is_staff and not user.is_superuser and profile.role == "student":
        profile.role = "teacher"
        profile.save(update_fields=["role"])
    progress = get_user_progress_summary(user)
    updated_level = get_level_info(progress["xp"])
    fields_to_update = []
    if profile.xp != progress["xp"]:
        profile.xp = progress["xp"]
        fields_to_update.append("xp")
    if profile.level != updated_level["label"]:
        profile.level = updated_level["label"]
        fields_to_update.append("level")
    if fields_to_update:
        profile.save(update_fields=fields_to_update)
    return profile


def get_effective_subject_level(user: User, subject_id: int | None = None, profile: Profile | None = None):
    fallback_level = (profile.level if profile else None) or get_or_sync_profile(user).level
    if not subject_id:
        return normalize_difficulty_label(fallback_level)

    preferred_level = (
        UserSubjectPreference.objects.filter(user=user, subject_id=subject_id)
        .values_list("preferred_level", flat=True)
        .first()
    )
    return normalize_difficulty_label(preferred_level or fallback_level)


def sidebar_context(user):
    profile = get_or_sync_profile(user)
    return {
        "profile": profile,
        "level_info": get_level_info(profile.xp),
        "xp_summary": get_user_progress_summary(user),
    }


def filter_by_allowed_level(queryset, field_name, profile_level):
    return queryset.filter(**{f"{field_name}__in": get_allowed_level_labels(profile_level)})


def resolve_section_return_url(next_url, fallback_url):
    if not next_url:
        return fallback_url
    normalized_next = str(next_url).strip()
    return normalized_next if normalized_next.startswith("/subjects/") else fallback_url


def get_user_progress_summary(user):
    test_attempts = UserTest.objects.filter(user=user)
    tests_xp = sum(
        int((attempt.snapshot_json or {}).get("xp_awarded", 0) or 0)
        for attempt in test_attempts
    )
    correct_test_answers = sum(max(0, attempt.correct_count or 0) for attempt in test_attempts)

    correct_practice_answers = (
        UserPracticeAttempt.objects.filter(
            user=user,
            is_correct=True,
        )
        .count()
    )

    practice_xp = correct_practice_answers * XP_PER_CORRECT_PRACTICE_ANSWER
    xp = tests_xp + practice_xp

    return {
        "xp": xp,
        "correct_tests": correct_test_answers,
        "correct_practice": correct_practice_answers,
        "tests_xp": tests_xp,
        "practice_xp": practice_xp,
    }
