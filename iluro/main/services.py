import json
import secrets
import string
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from .models import (
    Choice,
    EssayTopic,
    EssayTopicProgress,
    GrammarLessonProgress,
    GrammarLessonQuestion,
    PracticeChoice,
    PracticeExercise,
    PracticeSetAttempt,
    PracticeSet,
    Question,
    Profile,
    ReferralEvent,
    SubscriptionPlan,
    SubjectSectionEntry,
    Subject,
    Subscription,
    Test,
    UserAnswer,
    UserSubscription,
    UserSubscriptionSubject,
    UserDailyQuotaUsage,
    UserStatSummary,
    UserSubjectStat,
    UserPracticeAttempt,
    UserTest,
)
from .utils import (
    calculate_essay_topic_xp,
    calculate_grammar_lesson_xp,
    calculate_practice_set_xp,
    calculate_single_practice_xp,
    calculate_test_xp,
    get_allowed_level_labels,
    get_level_info,
    get_subject_level_info,
    normalize_difficulty_label,
)


ASSESSMENT_HISTORY_LIMIT = 5
TEST_ATTEMPT_RETENTION_DAYS = 7
REFERRAL_SESSION_KEY = "pending_referral_code"
REFERRAL_REWARD_PERCENT = 2
REFERRAL_MAX_AVAILABLE_PERCENT = 50
REFERRAL_REQUIRED_COMPLETIONS = 1
REFERRAL_ELIGIBLE_PLAN_CODES = {"single-subject", "triple-subject", "all-access"}
PROFILE_PHOTO_ELIGIBLE_PLAN_CODES = {"triple-subject", "all-access"}
REFERRAL_DISCOUNT_STACKS_WITH_PROMO = False
REFERRAL_CODE_ALPHABET = string.ascii_uppercase + string.digits
DEFAULT_SUBSCRIPTION_PLAN_CATALOG = [
    {
        "code": "free",
        "name": "FREE",
        "subject_limit": 1,
        "is_all_access": False,
        "price": 0,
        "duration_days": 30,
        "display_order": 10,
        "stack_mode": "replace",
        "daily_test_limit": 3,
        "daily_ai_limit": 3,
        "is_public": True,
        "is_featured": False,
        "can_use_ai": True,
        "can_use_full_content": False,
        "can_use_advanced_content": False,
        "can_use_mock_exam": False,
        "can_use_progress_recommendations": False,
        "can_use_advanced_stats": False,
        "is_active": True,
    },
    {
        "code": "single-subject",
        "name": "SINGLE SUBJECT",
        "subject_limit": 1,
        "is_all_access": False,
        "price": 30000,
        "duration_days": 30,
        "display_order": 20,
        "stack_mode": "additive",
        "daily_test_limit": None,
        "daily_ai_limit": None,
        "is_public": True,
        "is_featured": False,
        "can_use_ai": True,
        "can_use_full_content": True,
        "can_use_advanced_content": False,
        "can_use_mock_exam": False,
        "can_use_progress_recommendations": False,
        "can_use_advanced_stats": False,
        "is_active": True,
    },
    {
        "code": "triple-subject",
        "name": "PRO",
        "subject_limit": 3,
        "is_all_access": False,
        "price": 70000,
        "duration_days": 30,
        "display_order": 30,
        "stack_mode": "additive",
        "daily_test_limit": None,
        "daily_ai_limit": None,
        "is_public": True,
        "is_featured": True,
        "can_use_ai": True,
        "can_use_full_content": True,
        "can_use_advanced_content": True,
        "can_use_mock_exam": False,
        "can_use_progress_recommendations": True,
        "can_use_advanced_stats": False,
        "is_active": True,
    },
    {
        "code": "all-access",
        "name": "PREMIUM",
        "subject_limit": None,
        "is_all_access": True,
        "price": 120000,
        "duration_days": 30,
        "display_order": 40,
        "stack_mode": "replace",
        "daily_test_limit": None,
        "daily_ai_limit": None,
        "is_public": True,
        "is_featured": True,
        "can_use_ai": True,
        "can_use_full_content": True,
        "can_use_advanced_content": True,
        "can_use_mock_exam": True,
        "can_use_progress_recommendations": True,
        "can_use_advanced_stats": True,
        "is_active": True,
    },
    {
        "code": "beta-trial-all-access",
        "name": "Beta trial",
        "subject_limit": None,
        "is_all_access": True,
        "price": 0,
        "duration_days": 14,
        "display_order": 90,
        "stack_mode": "replace",
        "daily_test_limit": None,
        "daily_ai_limit": None,
        "is_public": False,
        "is_featured": False,
        "can_use_ai": True,
        "can_use_full_content": True,
        "can_use_advanced_content": True,
        "can_use_mock_exam": True,
        "can_use_progress_recommendations": True,
        "can_use_advanced_stats": True,
        "is_active": True,
    },
]


def _normalize_referral_code(value):
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())[:24]


def normalize_referral_wallet(profile, *, save=False):
    total_percent = max(int(profile.referral_discount_percent or 0), 0)
    used_percent = max(int(profile.referral_discount_used_percent or 0), 0)
    used_percent = min(used_percent, total_percent)
    max_available_percent = max(total_percent - used_percent, 0)
    available_percent = max(int(profile.referral_discount_available_percent or 0), 0)
    available_percent = min(available_percent, max_available_percent, REFERRAL_MAX_AVAILABLE_PERCENT)

    updated_fields = []
    if profile.referral_discount_percent != total_percent:
        profile.referral_discount_percent = total_percent
        updated_fields.append("referral_discount_percent")
    if profile.referral_discount_used_percent != used_percent:
        profile.referral_discount_used_percent = used_percent
        updated_fields.append("referral_discount_used_percent")
    if profile.referral_discount_available_percent != available_percent:
        profile.referral_discount_available_percent = available_percent
        updated_fields.append("referral_discount_available_percent")

    if save and updated_fields:
        profile.save(update_fields=updated_fields)
    return profile


def _generate_unique_referral_code():
    for _ in range(32):
        candidate = "".join(secrets.choice(REFERRAL_CODE_ALPHABET) for _ in range(8))
        if not Profile.objects.filter(referral_code=candidate).exists():
            return candidate
    raise RuntimeError("Referral code yaratib bo'lmadi.")


def ensure_profile_referral_code(profile, *, save=False):
    before_total = profile.referral_discount_percent
    before_used = profile.referral_discount_used_percent
    before_available = profile.referral_discount_available_percent
    updated_fields = []
    if not profile.referral_code:
        profile.referral_code = _generate_unique_referral_code()
        updated_fields.append("referral_code")
    normalize_referral_wallet(profile, save=False)
    if profile.referral_discount_percent != before_total:
        updated_fields.append("referral_discount_percent")
    if profile.referral_discount_used_percent != before_used:
        updated_fields.append("referral_discount_used_percent")
    if profile.referral_discount_available_percent != before_available:
        updated_fields.append("referral_discount_available_percent")
    if save and updated_fields:
        profile.save(update_fields=list(dict.fromkeys(updated_fields)))
    return profile


def get_total_referral_completion_count(user):
    completed_test_count = UserTest.objects.filter(
        user=user,
        snapshot_json__status="completed",
    ).count()
    completed_practice_set_count = PracticeSetAttempt.objects.filter(user=user).count()
    completed_single_practice_count = UserPracticeAttempt.objects.filter(
        user=user,
        practice_session__isnull=True,
    ).count()
    return completed_test_count + completed_practice_set_count + completed_single_practice_count


def credit_referral_discount(profile, percent):
    percent = max(int(percent or 0), 0)
    if percent <= 0:
        normalize_referral_wallet(profile, save=True)
        return 0

    normalize_referral_wallet(profile, save=False)
    available_room = max(REFERRAL_MAX_AVAILABLE_PERCENT - int(profile.referral_discount_available_percent or 0), 0)
    applied_percent = min(percent, available_room)
    if applied_percent <= 0:
        return 0

    profile.referral_discount_percent = int(profile.referral_discount_percent or 0) + applied_percent
    profile.referral_discount_available_percent = int(profile.referral_discount_available_percent or 0) + applied_percent
    profile.save(update_fields=["referral_discount_percent", "referral_discount_available_percent"])
    normalize_referral_wallet(profile, save=True)
    return applied_percent


def consume_referral_discount(profile):
    normalize_referral_wallet(profile, save=False)
    available_percent = int(profile.referral_discount_available_percent or 0)
    if available_percent <= 0:
        return 0

    profile.referral_discount_used_percent = int(profile.referral_discount_used_percent or 0) + available_percent
    profile.referral_discount_available_percent = 0
    profile.save(update_fields=["referral_discount_used_percent", "referral_discount_available_percent"])
    normalize_referral_wallet(profile, save=True)
    return available_percent


def stash_pending_referral_code(request, referral_code):
    normalized_code = _normalize_referral_code(referral_code)
    if not normalized_code:
        request.session.pop(REFERRAL_SESSION_KEY, None)
        return None
    request.session[REFERRAL_SESSION_KEY] = normalized_code
    return normalized_code


def get_pending_referral_code(request):
    return _normalize_referral_code(request.session.get(REFERRAL_SESSION_KEY))


def clear_pending_referral_code(request):
    request.session.pop(REFERRAL_SESSION_KEY, None)


@transaction.atomic
def register_referral_for_user(user, referral_code):
    normalized_code = _normalize_referral_code(referral_code)
    if not normalized_code:
        return None

    profile = Profile.objects.select_for_update().select_related("user").get(user=user)
    ensure_profile_referral_code(profile, save=True)
    if profile.referred_by_id:
        return ReferralEvent.objects.filter(invited_user=user).select_related("inviter").first()

    inviter_profile = (
        Profile.objects.select_for_update()
        .select_related("user")
        .filter(referral_code=normalized_code)
        .exclude(user_id=user.id)
        .first()
    )
    if inviter_profile is None:
        raise ValidationError("Referral code topilmadi.")
    if inviter_profile.user_id == user.id:
        raise ValidationError("O'zingizning referral code bilan ro'yxatdan o'tib bo'lmaydi.")

    profile.referred_by = inviter_profile.user
    profile.referred_at = timezone.now()
    profile.save(update_fields=["referred_by", "referred_at"])
    event, _ = ReferralEvent.objects.get_or_create(
        invited_user=user,
        defaults={
            "inviter": inviter_profile.user,
            "status": "pending",
            "reward_percent": 0,
        },
    )
    return event


@transaction.atomic
def evaluate_referral_qualification(user):
    event = (
        ReferralEvent.objects.select_for_update()
        .filter(invited_user=user)
        .first()
    )
    if event is None or event.status == "qualified":
        return event

    invited_profile = getattr(event.invited_user, "profile", None)
    if invited_profile is None:
        invited_profile = Profile.objects.select_for_update().get(user=event.invited_user)

    if not invited_profile.free_subject_id:
        return event
    if get_total_referral_completion_count(event.invited_user) < REFERRAL_REQUIRED_COMPLETIONS:
        return event

    inviter_profile = getattr(event.inviter, "profile", None)
    if inviter_profile is None:
        inviter_profile = Profile.objects.select_for_update().get(user=event.inviter)
    ensure_profile_referral_code(inviter_profile, save=True)

    reward_percent = credit_referral_discount(inviter_profile, REFERRAL_REWARD_PERCENT)
    event.status = "qualified"
    event.qualified_at = timezone.now()
    event.reward_percent = reward_percent
    event.save(update_fields=["status", "qualified_at", "reward_percent", "updated_at"])
    return event


def get_referral_plan_quote(plan, available_percent=0):
    base_price = int(getattr(plan, "price", 0) or 0)
    normalized_available = max(int(available_percent or 0), 0)
    eligible = bool(
        getattr(plan, "code", "") in REFERRAL_ELIGIBLE_PLAN_CODES
        and base_price > 0
    )
    applied_percent = normalized_available if eligible else 0
    discount_amount = (base_price * applied_percent) // 100 if applied_percent else 0
    return {
        "eligible": eligible,
        "base_price": base_price,
        "discount_percent": applied_percent,
        "discount_amount": discount_amount,
        "final_price": max(base_price - discount_amount, 0),
    }


@transaction.atomic
def apply_referral_discount_to_subscription(subscription):
    if not subscription.plan_id or subscription.referral_discount_percent_applied:
        return 0
    if subscription.source not in {"purchase", "manual"}:
        subscription.price_before_discount = int(subscription.plan.price or 0)
        subscription.final_price = int(subscription.plan.price or 0)
        subscription.save(update_fields=["price_before_discount", "final_price", "updated_at"])
        return 0

    profile = Profile.objects.select_for_update().get(user=subscription.user)
    normalize_referral_wallet(profile, save=True)
    quote = get_referral_plan_quote(subscription.plan, profile.referral_discount_available_percent)

    subscription.price_before_discount = quote["base_price"]
    subscription.referral_discount_percent_applied = quote["discount_percent"]
    subscription.referral_discount_amount = quote["discount_amount"]
    subscription.final_price = quote["final_price"]
    applied_percent = quote["discount_percent"]
    if applied_percent:
        consume_referral_discount(profile)
    subscription.save(
        update_fields=[
            "price_before_discount",
            "referral_discount_percent_applied",
            "referral_discount_amount",
            "final_price",
            "updated_at",
        ]
    )
    return applied_percent


def get_referral_summary(user):
    profile = get_or_sync_profile(user)
    ensure_profile_referral_code(profile, save=True)
    event = evaluate_referral_qualification(user)
    normalize_referral_wallet(profile, save=True)

    sent_events = ReferralEvent.objects.filter(inviter=user)
    completion_count = get_total_referral_completion_count(user)
    qualification_progress = None
    if event is not None:
        qualification_progress = {
            "status": event.status,
            "status_label": event.get_status_display(),
            "inviter_name": (
                getattr(getattr(event.inviter, "profile", None), "full_name", "")
                or event.inviter.first_name
                or event.inviter.username
            ),
            "free_subject_selected": bool(profile.free_subject_id),
            "completion_count": completion_count,
            "completion_target": REFERRAL_REQUIRED_COMPLETIONS,
            "completion_remaining": max(REFERRAL_REQUIRED_COMPLETIONS - completion_count, 0),
            "reward_percent": int(event.reward_percent or 0),
        }

    return {
        "referral_code": profile.referral_code,
        "available_percent": int(profile.referral_discount_available_percent or 0),
        "used_percent": int(profile.referral_discount_used_percent or 0),
        "total_percent": int(profile.referral_discount_percent or 0),
        "qualified_count": sent_events.filter(status="qualified").count(),
        "pending_count": sent_events.filter(status="pending").count(),
        "sent_count": sent_events.count(),
        "qualification_progress": qualification_progress,
        "required_completions": REFERRAL_REQUIRED_COMPLETIONS,
        "reward_percent": REFERRAL_REWARD_PERCENT,
        "max_percent": REFERRAL_MAX_AVAILABLE_PERCENT,
        "eligible_plan_names": ["SINGLE", "PRO", "PREMIUM"],
        "stacks_with_promo": REFERRAL_DISCOUNT_STACKS_WITH_PROMO,
    }


def rebuild_user_statistics(user):
    summary, _ = UserStatSummary.objects.get_or_create(user=user)
    manual_xp_adjustment = int(summary.manual_xp_adjustment or 0)

    user_tests = list(
        UserTest.objects.filter(user=user)
        .select_related("test")
        .order_by("-finished_at", "-started_at", "-id")
    )
    practice_sessions = list(
        PracticeSetAttempt.objects.filter(user=user)
        .select_related("practice_set", "practice_set__subject")
        .order_by("-created_at", "-id")
    )
    practice_attempts = list(
        UserPracticeAttempt.objects.filter(user=user)
        .select_related("exercise", "exercise__subject", "practice_session")
        .order_by("-created_at", "-id")
    )
    grammar_progress_rows = list(
        GrammarLessonProgress.objects.filter(user=user)
        .select_related("lesson", "lesson__subject")
        .order_by("-updated_at", "-id")
    )
    essay_progress_rows = list(
        EssayTopicProgress.objects.filter(user=user)
        .select_related("topic", "topic__subject")
        .order_by("-updated_at", "-id")
    )

    total_correct_test_answers = sum(max(0, attempt.correct_count or 0) for attempt in user_tests)
    total_correct_practice_answers = sum(1 for attempt in practice_attempts if attempt.is_correct)
    test_xp = 0
    practice_xp = 0
    grammar_xp = 0
    essay_xp = 0
    earned_xp = 0
    best_test_score = max((attempt.score or 0 for attempt in user_tests), default=0)
    session_best_practice = max((attempt.score or 0 for attempt in practice_sessions), default=0)
    single_best_practice = 100 if any(attempt.is_correct for attempt in practice_attempts if attempt.practice_session_id is None) else 0
    best_practice_score = max(session_best_practice, single_best_practice)
    grammar_completed_count = sum(1 for progress in grammar_progress_rows if progress.is_completed)
    essay_completed_count = sum(1 for progress in essay_progress_rows if progress.is_completed)

    last_activity_candidates = [
        attempt.finished_at or attempt.started_at
        for attempt in user_tests
        if attempt.finished_at or attempt.started_at
    ]
    last_activity_candidates.extend(attempt.created_at for attempt in practice_sessions if attempt.created_at)
    last_activity_candidates.extend(attempt.created_at for attempt in practice_attempts if attempt.created_at)
    last_activity_candidates.extend(progress.updated_at for progress in grammar_progress_rows if progress.updated_at)
    last_activity_candidates.extend(progress.updated_at for progress in essay_progress_rows if progress.updated_at)
    last_activity_at = max(last_activity_candidates, default=None)

    summary.lifetime_xp = 0
    summary.test_xp_total = 0
    summary.practice_xp_total = 0
    summary.grammar_xp_total = 0
    summary.essay_xp_total = 0
    summary.lifetime_test_count = len(user_tests)
    summary.lifetime_practice_count = len(practice_attempts)
    summary.total_grammar_lessons_completed = grammar_completed_count
    summary.total_essay_topics_completed = essay_completed_count
    summary.total_correct_answers = total_correct_test_answers + total_correct_practice_answers
    summary.total_correct_test_answers = total_correct_test_answers
    summary.total_correct_practice_answers = total_correct_practice_answers
    summary.best_test_score = best_test_score
    summary.best_practice_score = best_practice_score
    summary.last_activity_at = last_activity_at

    subject_stats = {}
    for attempt in user_tests:
        attempt_total_count = attempt.snapshot_json.get("question_count") or Question.objects.filter(test=attempt.test).count()
        attempt_xp = calculate_test_xp(
            attempt.correct_count,
            attempt_total_count,
            attempt.test.difficulty,
        )
        if attempt.snapshot_json.get("xp_awarded") != attempt_xp:
            attempt.snapshot_json = {**attempt.snapshot_json, "xp_awarded": attempt_xp}
            attempt.save(update_fields=["snapshot_json"])
        test_xp += attempt_xp
        earned_xp += attempt_xp
        subject_id = attempt.test.subject_id
        stats = subject_stats.setdefault(
            subject_id,
            {
                "subject": attempt.test.subject,
                "xp": 0,
                "tests_taken": 0,
                "practice_taken": 0,
                "total_correct_test_answers": 0,
                "total_correct_practice_answers": 0,
                "best_score": 0,
                "last_activity_at": None,
            },
        )
        stats["tests_taken"] += 1
        stats["total_correct_test_answers"] += max(0, attempt.correct_count or 0)
        stats["xp"] += attempt_xp
        stats["best_score"] = max(stats["best_score"], attempt.score or 0)
        attempt_time = attempt.finished_at or attempt.started_at
        if attempt_time and (stats["last_activity_at"] is None or attempt_time > stats["last_activity_at"]):
            stats["last_activity_at"] = attempt_time

    for attempt in practice_attempts:
        subject_id = attempt.exercise.subject_id
        stats = subject_stats.setdefault(
            subject_id,
            {
                "subject": attempt.exercise.subject,
                "xp": 0,
                "tests_taken": 0,
                "practice_taken": 0,
                "total_correct_test_answers": 0,
                "total_correct_practice_answers": 0,
                "best_score": 0,
                "last_activity_at": None,
            },
        )
        stats["practice_taken"] += 1
        if attempt.is_correct:
            stats["total_correct_practice_answers"] += 1
            if attempt.practice_session_id is None:
                attempt_xp = calculate_single_practice_xp(attempt.is_correct, attempt.exercise.difficulty)
                stats["xp"] += attempt_xp
                practice_xp += attempt_xp
                earned_xp += attempt_xp
                stats["best_score"] = max(stats["best_score"], 100)
        if attempt.created_at and (stats["last_activity_at"] is None or attempt.created_at > stats["last_activity_at"]):
            stats["last_activity_at"] = attempt.created_at

    for session in practice_sessions:
        session_xp = calculate_practice_set_xp(
            session.correct_count,
            session.total_count,
            session.practice_set.difficulty,
        )
        practice_xp += session_xp
        earned_xp += session_xp
        subject_id = session.practice_set.subject_id
        stats = subject_stats.setdefault(
            subject_id,
            {
                "subject": session.practice_set.subject,
                "xp": 0,
                "tests_taken": 0,
                "practice_taken": 0,
                "total_correct_test_answers": 0,
                "total_correct_practice_answers": 0,
                "best_score": 0,
                "last_activity_at": None,
            },
        )
        stats["xp"] += session_xp
        stats["best_score"] = max(stats["best_score"], session.score or 0)
        if session.created_at and (stats["last_activity_at"] is None or session.created_at > stats["last_activity_at"]):
            stats["last_activity_at"] = session.created_at

    for progress in grammar_progress_rows:
        progress_xp = calculate_grammar_lesson_xp(
            progress.best_score,
            progress.lesson.access_level,
            progress.is_completed,
            progress.attempts_count > 0,
        )
        if progress.xp_awarded != progress_xp:
            progress.xp_awarded = progress_xp
            progress.save(update_fields=["xp_awarded", "updated_at"])
        grammar_xp += progress_xp
        earned_xp += progress_xp
        subject_id = progress.lesson.subject_id
        stats = subject_stats.setdefault(
            subject_id,
            {
                "subject": progress.lesson.subject,
                "xp": 0,
                "tests_taken": 0,
                "practice_taken": 0,
                "total_correct_test_answers": 0,
                "total_correct_practice_answers": 0,
                "best_score": 0,
                "last_activity_at": None,
            },
        )
        stats["xp"] += progress_xp
        stats["best_score"] = max(stats["best_score"], progress.best_score or 0)
        if progress.updated_at and (stats["last_activity_at"] is None or progress.updated_at > stats["last_activity_at"]):
            stats["last_activity_at"] = progress.updated_at

    for progress in essay_progress_rows:
        progress_xp = calculate_essay_topic_xp(
            progress.topic.access_level,
            progress.is_completed,
            progress.topic.is_featured,
        )
        if progress.xp_awarded != progress_xp:
            progress.xp_awarded = progress_xp
            progress.save(update_fields=["xp_awarded", "updated_at"])
        essay_xp += progress_xp
        earned_xp += progress_xp
        subject_id = progress.topic.subject_id
        stats = subject_stats.setdefault(
            subject_id,
            {
                "subject": progress.topic.subject,
                "xp": 0,
                "tests_taken": 0,
                "practice_taken": 0,
                "total_correct_test_answers": 0,
                "total_correct_practice_answers": 0,
                "best_score": 0,
                "last_activity_at": None,
            },
        )
        stats["xp"] += progress_xp
        if progress.updated_at and (stats["last_activity_at"] is None or progress.updated_at > stats["last_activity_at"]):
            stats["last_activity_at"] = progress.updated_at

    summary.lifetime_xp = max(0, earned_xp + manual_xp_adjustment)
    summary.test_xp_total = test_xp
    summary.practice_xp_total = practice_xp
    summary.grammar_xp_total = grammar_xp
    summary.essay_xp_total = essay_xp
    summary.total_grammar_lessons_completed = grammar_completed_count
    summary.total_essay_topics_completed = essay_completed_count
    summary.save(
        update_fields=[
            "lifetime_xp",
            "manual_xp_adjustment",
            "test_xp_total",
            "practice_xp_total",
            "grammar_xp_total",
            "essay_xp_total",
            "total_grammar_lessons_completed",
            "total_essay_topics_completed",
            "updated_at",
        ]
    )

    UserSubjectStat.objects.filter(user=user).exclude(subject_id__in=subject_stats.keys()).delete()
    for subject_id, stats in subject_stats.items():
        total_correct_answers = stats["total_correct_test_answers"] + stats["total_correct_practice_answers"]
        UserSubjectStat.objects.update_or_create(
            user=user,
            subject=stats["subject"],
            defaults={
                "xp": stats["xp"],
                "tests_taken": stats["tests_taken"],
                "practice_taken": stats["practice_taken"],
                "total_correct_answers": total_correct_answers,
                "total_correct_test_answers": stats["total_correct_test_answers"],
                "total_correct_practice_answers": stats["total_correct_practice_answers"],
                "best_score": stats["best_score"],
                "last_activity_at": stats["last_activity_at"],
            },
        )

    return summary


def get_user_stat_summary(user):
    summary = getattr(user, "stat_summary", None)
    if summary is not None:
        return summary
    return rebuild_user_statistics(user)


def record_test_completion_stats(user_test):
    result = rebuild_user_statistics(user_test.user)
    evaluate_referral_qualification(user_test.user)
    return result


def record_practice_session_completion_stats(practice_session):
    result = rebuild_user_statistics(practice_session.user)
    evaluate_referral_qualification(practice_session.user)
    return result


def record_single_practice_attempt_stats(attempt):
    result = rebuild_user_statistics(attempt.user)
    evaluate_referral_qualification(attempt.user)
    return result


def trim_user_assessment_history(user, keep_recent=ASSESSMENT_HISTORY_LIMIT):
    keep_recent = max(int(keep_recent or ASSESSMENT_HISTORY_LIMIT), 1)
    now = timezone.now()
    cutoff = now - timedelta(days=TEST_ATTEMPT_RETENTION_DAYS)

    kept_test_ids = list(
        UserTest.objects.filter(user=user)
        .filter(Q(finished_at__gte=cutoff) | Q(started_at__gte=cutoff))
        .order_by("-finished_at", "-started_at", "-id")
        .values_list("id", flat=True)
    )
    if kept_test_ids:
        UserTest.objects.filter(user=user).exclude(id__in=kept_test_ids).delete()
        kept_test_subject_ids = UserTest.objects.filter(id__in=kept_test_ids).values_list("test_id", flat=True)
        kept_question_ids = Question.objects.filter(test_id__in=kept_test_subject_ids).values_list("id", flat=True)
        UserAnswer.objects.filter(user=user).exclude(question_id__in=kept_question_ids).delete()
    else:
        UserTest.objects.filter(user=user).delete()
        UserAnswer.objects.filter(user=user).delete()

    kept_session_ids = list(
        PracticeSetAttempt.objects.filter(user=user, created_at__gte=cutoff)
        .order_by("-created_at", "-id")
        .values_list("id", flat=True)
    )
    if kept_session_ids:
        PracticeSetAttempt.objects.filter(user=user).exclude(id__in=kept_session_ids).delete()
    else:
        PracticeSetAttempt.objects.filter(user=user).delete()

    kept_attempt_ids = []
    latest_wrong_attempt_map = {}
    for attempt in (
        UserPracticeAttempt.objects.filter(user=user, is_correct=False)
        .order_by("exercise_id", "-created_at", "-id")
        .values("id", "exercise_id")
    ):
        exercise_id = attempt["exercise_id"]
        if exercise_id in latest_wrong_attempt_map:
            continue
        latest_wrong_attempt_map[exercise_id] = attempt["id"]
        kept_attempt_ids.append(attempt["id"])

    if kept_attempt_ids:
        UserPracticeAttempt.objects.filter(user=user).exclude(id__in=kept_attempt_ids).delete()
    else:
        UserPracticeAttempt.objects.filter(user=user).delete()

    active_session_ids = set(kept_session_ids)
    active_session_ids.update(
        UserPracticeAttempt.objects.filter(user=user, practice_session__isnull=False).values_list(
            "practice_session_id",
            flat=True,
        )
    )
    if active_session_ids:
        PracticeSetAttempt.objects.filter(user=user).exclude(id__in=list(active_session_ids)).delete()
    else:
        PracticeSetAttempt.objects.filter(user=user).delete()


def ensure_default_subscription_plans():
    plans = {}
    for item in DEFAULT_SUBSCRIPTION_PLAN_CATALOG:
        plan, _ = SubscriptionPlan.objects.update_or_create(
            code=item["code"],
            defaults=item,
        )
        plans[item["code"]] = plan

    SubscriptionPlan.objects.filter(code="double-subject").update(
        name="Legacy 2 fan",
        is_active=False,
        is_public=False,
        is_featured=False,
        display_order=80,
    )
    return plans


def create_user_beta_trial_subscription(user, end_at=None):
    plans = ensure_default_subscription_plans()
    plan = plans["beta-trial-all-access"]
    end_at = end_at or (timezone.now() + timedelta(days=plan.duration_days))
    return UserSubscription.objects.create(
        user=user,
        plan=plan,
        title=plan.name,
        source="beta_trial",
        status="active",
        is_all_access=True,
        started_at=timezone.now(),
        end_at=end_at,
    )


def cleanup_empty_user_subscriptions(subscription_ids=None):
    queryset = UserSubscription.objects.filter(is_all_access=False)
    if subscription_ids is not None:
        queryset = queryset.filter(id__in=list(subscription_ids))

    empty_ids = []
    for subscription in queryset.prefetch_related("subjects"):
        if not subscription.subjects.exists():
            empty_ids.append(subscription.id)

    if empty_ids:
        UserSubscription.objects.filter(id__in=empty_ids).delete()

    return empty_ids


def get_free_plan():
    return ensure_default_subscription_plans()["free"]


def assign_free_subject(user, subject):
    profile = get_or_sync_profile(user)
    subject_obj = subject if hasattr(subject, "id") else Subject.objects.get(id=int(subject))

    if profile.free_subject_id and profile.free_subject_id != subject_obj.id:
        raise ValidationError("Free fan allaqachon tanlangan va o'zgarmaydi.")

    if not profile.free_subject_id:
        profile.free_subject = subject_obj
        profile.free_subject_locked_at = timezone.now()
        profile.save(update_fields=["free_subject", "free_subject_locked_at"])
        evaluate_referral_qualification(user)

    return profile


def user_requires_free_subject_selection(user):
    profile = get_or_sync_profile(user)
    if profile.free_subject_id:
        return False
    return not bool(get_user_subject_access_rows(user, active_only=True))


def _append_free_subject_access_row(access_map, user):
    now = timezone.now()
    profile = Profile.objects.filter(user=user).select_related("free_subject").first()
    if not profile or not profile.free_subject_id:
        return
    existing = access_map.get(profile.free_subject_id)
    if existing and existing.get("is_permanent"):
        return
    if existing and existing.get("end_at") and existing["end_at"] >= now:
        return

    access_map[profile.free_subject_id] = {
        "subject": profile.free_subject,
        "subject_id": profile.free_subject_id,
        "end_at": None,
        "source": "free",
        "is_permanent": True,
    }


def get_current_subscription_plan(user):
    now = timezone.now()
    active_plan = (
        UserSubscription.objects.filter(
            user=user,
            status="active",
            end_at__gte=now,
            plan__isnull=False,
        )
        .select_related("plan")
        .order_by("-plan__is_all_access", "-plan__subject_limit", "-plan__price", "plan__display_order")
        .first()
    )
    if active_plan and active_plan.plan:
        return active_plan.plan
    if Subscription.objects.filter(user=user, end_date__gte=now).exists():
        return None
    profile = getattr(user, "profile", None)
    if profile is None:
        profile = Profile.objects.filter(user=user).only("free_subject_id").first()
    if profile and profile.free_subject_id:
        return get_free_plan()
    return None


def user_can_upload_profile_photo(user):
    plan = get_current_subscription_plan(user)
    return bool(plan and getattr(plan, "code", "") in PROFILE_PHOTO_ELIGIBLE_PLAN_CODES)


def get_daily_quota_usage(user, current_date=None):
    current_date = current_date or timezone.localdate()
    usage, _ = UserDailyQuotaUsage.objects.get_or_create(user=user, date=current_date)
    return usage


def get_daily_assessment_limit(user):
    plan = get_current_subscription_plan(user)
    if not plan:
        return None
    return plan.daily_test_limit


def ensure_daily_assessment_quota_available(user):
    limit = get_daily_assessment_limit(user)
    if limit is None:
        return None
    usage = get_daily_quota_usage(user)
    if usage.tests_started >= limit:
        raise ValidationError(f"Bugungi limit tugadi. Free rejada kuniga {limit} ta assessment ishlash mumkin.")
    return usage


def register_daily_assessment_start(user):
    usage = get_daily_quota_usage(user)
    usage.tests_started += 1
    usage.save(update_fields=["tests_started", "updated_at"])
    return usage


def revoke_subject_access(user, subject, include_legacy=True, include_bundle=True):
    user_id = user.id if hasattr(user, "id") else int(user)
    subject_id = subject.id if hasattr(subject, "id") else int(subject)

    if include_legacy:
        Subscription.objects.filter(user_id=user_id, subject_id=subject_id).delete()

    affected_subscription_ids = []
    if include_bundle:
        affected_subscription_ids = list(
            UserSubscriptionSubject.objects.filter(
                subscription__user_id=user_id,
                subject_id=subject_id,
            )
            .values_list("subscription_id", flat=True)
            .distinct()
        )
        UserSubscriptionSubject.objects.filter(
            subscription__user_id=user_id,
            subject_id=subject_id,
        ).delete()
        cleanup_empty_user_subscriptions(affected_subscription_ids)

    return affected_subscription_ids


def get_user_subject_access_rows(user, active_only=False):
    now = timezone.now()
    access_map = {}

    bundle_rows = UserSubscription.objects.filter(user=user)
    has_bundle_rows = bundle_rows.exists()
    bundle_rows = bundle_rows.prefetch_related("subjects__subject")
    if active_only:
        bundle_rows = bundle_rows.filter(status="active", end_at__gte=now)

    all_subjects_cache = None
    for subscription in bundle_rows:
        if subscription.is_all_access:
            if all_subjects_cache is None:
                all_subjects_cache = list(Subject.objects.all())
            for subject in all_subjects_cache:
                existing = access_map.get(subject.id)
                existing_end_at = existing["end_at"] if existing else None
                if existing is None or existing_end_at is None or subscription.end_at > existing_end_at:
                    access_map[subject.id] = {
                        "subject": subject,
                        "subject_id": subject.id,
                        "end_at": subscription.end_at,
                        "source": "bundle",
                        "is_permanent": False,
                    }
            continue

        for item in subscription.subjects.all():
            existing = access_map.get(item.subject_id)
            existing_end_at = existing["end_at"] if existing else None
            if existing is None or existing_end_at is None or subscription.end_at > existing_end_at:
                access_map[item.subject_id] = {
                    "subject": item.subject,
                    "subject_id": item.subject_id,
                    "end_at": subscription.end_at,
                    "source": "bundle",
                    "is_permanent": False,
                }

    _append_free_subject_access_row(access_map, user)
    if has_bundle_rows:
        rows = list(access_map.values())
        rows.sort(key=lambda item: item["subject"].name)
        return rows

    legacy_rows = Subscription.objects.filter(user=user).select_related("subject")
    if active_only:
        legacy_rows = legacy_rows.filter(end_date__gte=now)

    for row in legacy_rows:
        existing = access_map.get(row.subject_id)
        existing_end_at = existing["end_at"] if existing else None
        if existing is None or existing_end_at is None or row.end_date > existing_end_at:
            access_map[row.subject_id] = {
                "subject": row.subject,
                "subject_id": row.subject_id,
                "end_at": row.end_date,
                "source": "legacy",
                "is_permanent": False,
            }

    _append_free_subject_access_row(access_map, user)
    rows = list(access_map.values())
    rows.sort(key=lambda item: item["subject"].name)
    return rows


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
                {"key": "formula-quiz", "label": "Formula savol-javob"},
                {"key": "problems", "label": "Misol / Masalalar"},
                {"key": "mistakes", "label": "Mening xatolarim"},
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
                {"key": "problems", "label": "Mashqlar"},
                {"key": "chronology", "label": "Xronologiya"},
                {"key": "terms", "label": "Atamalar"},
                {"key": "events", "label": "Sanalar / Voqealar"},
            ],
        }

    return {
        "key": "language",
        "eyebrow": "Matn va esse",
        "headline": "Grammatika, tahlil va esse yozishga mos sokin workspace.",
        "description": "Ona tili va adabiyot bo'limida matn bilan ishlash, grammatik tozalikni oshirish va milliy sertifikat uchun esse strukturasini kuchaytirish asosiy yo'nalish bo'ladi.",
        "stat_label": "Matn rejimi",
        "stat_value": "Esse",
        "cards": [
            {"title": "Bugungi fokus", "text": "Matnni to'g'ri qurish, uslubni silliqlash va fikrni ravshan berish."},
            {"title": "Mashq usuli", "text": "Grammatika testlari va esse outline'ini parallel ishlatish."},
            {"title": "AI yo'nalishi", "text": "Esse uchun reja, xato tahlili va jumla takomillashtirish."},
        ],
        "extra_sections": [
            {"key": "problems", "label": "Mashqlar"},
            {"key": "grammar", "label": "Grammatika"},
            {"key": "rules", "label": "Qoidalar"},
            {"key": "essay", "label": "Esse"},
            {"key": "extras", "label": "Qo'shimcha ma'lumotlar"},
        ],
    }


def import_test_from_json_payload(payload, *, subject_override=None, replace=False):
    if not isinstance(payload, dict):
        raise ValidationError("JSON top-level dict bo'lishi kerak.")

    title = (payload.get("title") or "").strip()
    difficulty = normalize_difficulty_label((payload.get("difficulty") or "").strip())
    category = (payload.get("category") or "general").strip() or "general"
    duration = int(payload.get("duration_minutes") or 40)
    questions = payload.get("questions") or []
    derived_answer_key = payload.get("derived_answer_key") or {}

    if not title:
        raise ValidationError("JSON ichida title majburiy.")
    if not difficulty:
        raise ValidationError("JSON ichida difficulty majburiy.")
    if not questions:
        raise ValidationError("JSON ichida questions bo'sh.")

    subject_ref = subject_override or payload.get("subject_name") or payload.get("subject_slug")
    subject = resolve_subject_ref(subject_ref)

    valid_difficulties = {choice[0] for choice in Test._meta.get_field("difficulty").choices}
    if difficulty not in valid_difficulties:
        raise ValidationError(
            f"Noto'g'ri difficulty: {difficulty}. Mavjudlari: {', '.join(sorted(valid_difficulties))}"
        )

    valid_categories = {choice[0] for choice in Test._meta.get_field("category").choices}
    if category not in valid_categories:
        raise ValidationError(
            f"Noto'g'ri category: {category}. Mavjudlari: {', '.join(sorted(valid_categories))}"
        )

    with transaction.atomic():
        test = (
            Test.objects.filter(subject=subject, title=title, difficulty=difficulty)
            .order_by("-id")
            .first()
        )
        created = False

        if test:
            if not replace:
                raise ValidationError(
                    "Shu subject/title/difficulty bilan test allaqachon mavjud. "
                    "Qayta yozish uchun replace yoqing."
                )
            test.category = category
            test.duration = duration
            test.save(update_fields=["category", "duration"])
            Question.objects.filter(test=test).delete()
        else:
            test = Test.objects.create(
                subject=subject,
                title=title,
                duration=duration,
                difficulty=difficulty,
                category=category,
            )
            created = True

        created_questions = 0
        created_choices = 0

        for index, item in enumerate(questions, start=1):
            if not isinstance(item, dict):
                raise ValidationError(f"{index}-savol dict emas.")

            number = item.get("number", index)
            text = (item.get("text") or "").strip()
            choices_map = item.get("choices") or {}
            correct_option = (item.get("correct_option") or derived_answer_key.get(str(number)) or "").strip().upper()

            if not text:
                raise ValidationError(f"{number}-savol uchun text majburiy.")
            if not isinstance(choices_map, dict) or len(choices_map) < 2:
                raise ValidationError(f"{number}-savol uchun kamida 2 ta variant kerak.")
            if correct_option not in choices_map:
                raise ValidationError(f"{number}-savol uchun correct_option topilmadi yoki variantlarda yo'q.")

            question = Question.objects.create(
                test=test,
                text=text,
                difficulty=difficulty,
            )
            created_questions += 1

            for option_key, option_text in choices_map.items():
                option_key_normalized = str(option_key).strip().upper()
                Choice.objects.create(
                    question=question,
                    text=str(option_text).strip(),
                    is_correct=option_key_normalized == correct_option,
                )
                created_choices += 1

    return {
        "test": test,
        "subject": subject,
        "created": created,
        "created_questions": created_questions,
        "created_choices": created_choices,
    }


def _convert_test_payload_to_practice_payload(payload):
    if not isinstance(payload, dict):
        raise ValidationError("Assessment import uchun JSON dict bo'lishi kerak.")

    title = (payload.get("title") or "").strip()
    difficulty = normalize_difficulty_label((payload.get("difficulty") or "C").strip() or "C")
    questions = payload.get("questions") or []
    derived_answer_key = payload.get("derived_answer_key") or {}

    if not title:
        raise ValidationError("JSON ichida title majburiy.")
    if not questions:
        raise ValidationError("JSON ichida questions bo'sh.")

    exercises = []
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"{index}-savol dict emas.")

        prompt = (item.get("text") or "").strip()
        if not prompt:
            raise ValidationError(f"{index}-savol uchun text majburiy.")

        choices_map = item.get("choices") or {}
        correct_option = (
            (item.get("correct_option") or derived_answer_key.get(str(item.get("number", index))) or "")
            .strip()
            .upper()
        )
        if not isinstance(choices_map, dict) or len(choices_map) < 2:
            raise ValidationError(f"{index}-savol uchun kamida 2 ta variant kerak.")
        if correct_option not in choices_map:
            raise ValidationError(f"{index}-savol uchun correct_option variantlarda topilmadi.")

        exercises.append(
            {
                "title": f"{index}-topshiriq",
                "prompt": prompt,
                "answer_mode": "choice",
                "difficulty": difficulty,
                "choices": [
                    {
                        "text": str(choice_text).strip(),
                        "is_correct": str(choice_key).strip().upper() == correct_option,
                    }
                    for choice_key, choice_text in choices_map.items()
                ],
            }
        )

    return {
        "title": title,
        "difficulty": difficulty,
        "topic": (payload.get("topic") or title).strip(),
        "description": (payload.get("description") or "Assessment import orqali yuklandi.").strip(),
        "source_book": (payload.get("source_book") or "").strip(),
        "is_featured": bool(payload.get("is_featured", False)),
        "exercises": exercises,
    }


def import_assessment_from_payload(payload, *, subject_override=None, replace=False):
    if isinstance(payload, dict) and "questions" in payload:
        payload = _convert_test_payload_to_practice_payload(payload)
    return import_practice_sets_from_payload(payload, subject_override=subject_override, replace=replace)


def load_json_payload_from_text(raw_text):
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"JSON format xato: {exc}") from exc
    if not isinstance(payload, (dict, list)):
        raise ValidationError("JSON top-level dict yoki list bo'lishi kerak.")
    return payload


def resolve_subject_ref(subject_ref):
    if isinstance(subject_ref, Subject):
        return subject_ref

    if not subject_ref:
        raise ValidationError("Fan topilmadi. JSON ichida subject_name yoki subject override kerak.")

    if str(subject_ref).isdigit():
        subject = Subject.objects.filter(id=int(subject_ref)).first()
    else:
        subject = Subject.objects.filter(name__iexact=str(subject_ref)).first()
        if not subject:
            subject = Subject.objects.filter(name__icontains=str(subject_ref)).first()

    if not subject:
        raise ValidationError(f"Fan topilmadi: {subject_ref}")

    return subject


def import_subject_entries_from_payload(payload, *, subject_override=None, section_key=None, clear_section=False):
    if isinstance(payload, dict):
        if "entries" in payload:
            entries = payload.get("entries") or []
            subject_ref = subject_override or payload.get("subject") or payload.get("subject_name")
            section_value = section_key or payload.get("section_key")
        else:
            entries = [payload]
            subject_ref = subject_override
            section_value = section_key
    elif isinstance(payload, list):
        entries = payload
        subject_ref = subject_override
        section_value = section_key
    else:
        raise ValidationError("Section import uchun JSON dict yoki list bo'lishi kerak.")

    if not entries:
        raise ValidationError("Import qilinadigan entries topilmadi.")

    subject = resolve_subject_ref(subject_ref)
    if not section_value:
        raise ValidationError("section_key topilmadi.")

    valid_sections = {choice[0] for choice in SubjectSectionEntry.SECTION_CHOICES}
    if section_value not in valid_sections:
        raise ValidationError(
            f"Noto'g'ri section key: {section_value}. Mavjudlari: {', '.join(sorted(valid_sections))}"
        )

    deleted_count = 0
    if clear_section:
        deleted_count, _ = SubjectSectionEntry.objects.filter(
            subject=subject,
            section_key=section_value,
        ).delete()

    created_count = 0
    updated_count = 0

    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValidationError(f"{index}-entry dict emas.")

        title = (entry.get("title") or "").strip()
        if not title:
            raise ValidationError(f"{index}-entry uchun title majburiy.")

        defaults = {
            "summary": (entry.get("summary") or "").strip(),
            "body": (entry.get("body") or "").strip(),
            "usage_note": (entry.get("usage_note") or "").strip(),
            "access_level": normalize_difficulty_label((entry.get("access_level") or "C").strip() or "C"),
            "order": entry.get("order", index),
            "is_featured": bool(entry.get("is_featured", False)),
        }

        _, created = SubjectSectionEntry.objects.update_or_create(
            subject=subject,
            section_key=section_value,
            title=title,
            defaults=defaults,
        )

        if created:
            created_count += 1
        else:
            updated_count += 1

    return {
        "subject": subject,
        "section_key": section_value,
        "created_count": created_count,
        "updated_count": updated_count,
        "deleted_count": deleted_count,
    }


def import_grammar_topics_from_payload(payload, *, subject_override=None, clear_existing=False):
    if not isinstance(payload, dict):
        raise ValidationError("Grammar import uchun JSON top-level dict bo'lishi kerak.")

    topics = payload.get("topics") or []
    if not topics:
        raise ValidationError("JSON ichida topics bo'sh.")

    subject_ref = subject_override or payload.get("subject_name") or payload.get("subject")
    subject = resolve_subject_ref(subject_ref)
    access_level = normalize_difficulty_label((payload.get("access_level") or "C").strip() or "C")
    valid_levels = {choice[0] for choice in SubjectSectionEntry._meta.get_field("access_level").choices}
    if access_level not in valid_levels:
        raise ValidationError(
            f"Noto'g'ri access_level: {access_level}. Mavjudlari: {', '.join(sorted(valid_levels))}"
        )

    deleted_count = 0
    if clear_existing:
        deleted_count, _ = SubjectSectionEntry.objects.filter(
            subject=subject,
            section_key="grammar",
        ).delete()

    created_count = 0
    updated_count = 0
    question_count = 0

    for index, item in enumerate(topics, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"{index}-topic dict emas.")

        title = (item.get("title") or "").strip()
        summary = (item.get("summary") or "").strip()
        body = (item.get("body") or "").strip()
        usage_note = (item.get("usage_note") or "").strip()
        questions = item.get("questions") or []

        if not title:
            raise ValidationError(f"{index}-topic uchun title majburiy.")
        if not questions:
            raise ValidationError(f"{title} uchun kamida 1 ta savol kerak.")

        lesson, created = SubjectSectionEntry.objects.update_or_create(
            subject=subject,
            section_key="grammar",
            title=title,
            defaults={
                "summary": summary,
                "body": body,
                "usage_note": usage_note,
                "access_level": normalize_difficulty_label((item.get("access_level") or access_level).strip() or access_level),
                "order": item.get("order", index),
                "is_featured": bool(item.get("is_featured", False)),
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

        lesson.grammar_questions.all().delete()

        for question_order, question in enumerate(questions, start=1):
            if not isinstance(question, dict):
                raise ValidationError(f"{title} mavzusidagi {question_order}-savol dict emas.")

            prompt = (question.get("prompt") or "").strip()
            option_a = (question.get("option_a") or "").strip()
            option_b = (question.get("option_b") or "").strip()
            option_c = (question.get("option_c") or "").strip()
            option_d = (question.get("option_d") or "").strip()
            correct_option = (question.get("correct_option") or "").strip().upper()

            if not prompt:
                raise ValidationError(f"{title} mavzusidagi {question_order}-savol uchun prompt majburiy.")
            if not all([option_a, option_b, option_c, option_d]):
                raise ValidationError(f"{title} mavzusidagi {question_order}-savol uchun barcha 4 variant majburiy.")
            if correct_option not in {"A", "B", "C", "D"}:
                raise ValidationError(f"{title} mavzusidagi {question_order}-savol uchun correct_option A/B/C/D bo'lishi kerak.")

            GrammarLessonQuestion.objects.create(
                lesson=lesson,
                prompt=prompt,
                option_a=option_a,
                option_b=option_b,
                option_c=option_c,
                option_d=option_d,
                correct_option=correct_option,
                explanation=(question.get("explanation") or "").strip(),
                order=question.get("order", question_order),
            )
            question_count += 1

    return {
        "subject": subject,
        "created_count": created_count,
        "updated_count": updated_count,
        "question_count": question_count,
        "deleted_count": deleted_count,
    }


def import_essay_topics_from_payload(payload, *, subject_override=None, clear_existing=False):
    if isinstance(payload, dict):
        topics = payload.get("topics") or payload.get("entries") or [payload]
        subject_ref = subject_override or payload.get("subject_name") or payload.get("subject")
        default_access_level = normalize_difficulty_label((payload.get("access_level") or "C").strip() or "C")
    elif isinstance(payload, list):
        topics = payload
        subject_ref = subject_override
        default_access_level = "C"
    else:
        raise ValidationError("Essay import uchun JSON dict yoki list bo'lishi kerak.")

    if not topics:
        raise ValidationError("Essay topic entries topilmadi.")

    subject = resolve_subject_ref(subject_ref)

    deleted_count = 0
    if clear_existing:
        deleted_count, _ = EssayTopic.objects.filter(subject=subject).delete()

    created_count = 0
    updated_count = 0

    for index, item in enumerate(topics, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"{index}-essay dict emas.")

        title = (item.get("title") or "").strip()
        prompt_text = (item.get("prompt_text") or item.get("body") or "").strip()
        if not title or not prompt_text:
            raise ValidationError(f"{index}-essay uchun title va prompt_text majburiy.")

        _, created = EssayTopic.objects.update_or_create(
            subject=subject,
            title=title,
            defaults={
                "prompt_text": prompt_text,
                "thesis_hint": (item.get("thesis_hint") or "").strip(),
                "outline": (item.get("outline") or "").strip(),
                "sample_intro": (item.get("sample_intro") or "").strip(),
                "sample_conclusion": (item.get("sample_conclusion") or "").strip(),
                "access_level": normalize_difficulty_label((item.get("access_level") or default_access_level).strip() or default_access_level),
                "is_featured": bool(item.get("is_featured", False)),
            },
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

    return {
        "subject": subject,
        "created_count": created_count,
        "updated_count": updated_count,
        "deleted_count": deleted_count,
    }


def import_practice_sets_from_payload(payload, *, subject_override=None, replace=False):
    if isinstance(payload, dict):
        if "sets" in payload:
            sets = payload.get("sets") or []
            subject_ref = subject_override or payload.get("subject_name") or payload.get("subject")
            default_difficulty = normalize_difficulty_label((payload.get("difficulty") or "C").strip() or "C")
        else:
            sets = [payload]
            subject_ref = subject_override or payload.get("subject_name") or payload.get("subject")
            default_difficulty = normalize_difficulty_label((payload.get("difficulty") or "C").strip() or "C")
    elif isinstance(payload, list):
        sets = payload
        subject_ref = subject_override
        default_difficulty = "C"
    else:
        raise ValidationError("Mashqlar importi uchun JSON dict yoki list bo'lishi kerak.")

    if not sets:
        raise ValidationError("Mashqlar importi uchun sets topilmadi.")

    subject = resolve_subject_ref(subject_ref)
    valid_difficulties = {choice[0] for choice in PracticeSet._meta.get_field("difficulty").choices}

    created_sets = 0
    updated_sets = 0
    created_exercises = 0
    created_choices = 0

    with transaction.atomic():
        for index, item in enumerate(sets, start=1):
            if not isinstance(item, dict):
                raise ValidationError(f"{index}-set dict emas.")

            title = (item.get("title") or "").strip()
            if not title:
                raise ValidationError(f"{index}-set uchun title majburiy.")

            difficulty = normalize_difficulty_label((item.get("difficulty") or default_difficulty).strip() or default_difficulty)
            if difficulty not in valid_difficulties:
                raise ValidationError(
                    f"Noto'g'ri difficulty: {difficulty}. Mavjudlari: {', '.join(sorted(valid_difficulties))}"
                )

            exercises = item.get("exercises") or []
            if not exercises:
                raise ValidationError(f"{title} uchun kamida 1 ta exercise kerak.")

            practice_set = (
                PracticeSet.objects.filter(subject=subject, title=title, difficulty=difficulty)
                .order_by("-id")
                .first()
            )

            if practice_set:
                if not replace:
                    raise ValidationError(
                        f"{title} ({difficulty}) allaqachon mavjud. Yangilash uchun replace yoqing."
                    )
                practice_set.source_book = (item.get("source_book") or "").strip()
                practice_set.topic = (item.get("topic") or "").strip()
                practice_set.description = (item.get("description") or "").strip()
                practice_set.is_featured = bool(item.get("is_featured", False))
                practice_set.save(update_fields=["source_book", "topic", "description", "is_featured"])
                practice_set.exercises.all().delete()
                updated_sets += 1
            else:
                practice_set = PracticeSet.objects.create(
                    subject=subject,
                    title=title,
                    source_book=(item.get("source_book") or "").strip(),
                    topic=(item.get("topic") or "").strip(),
                    description=(item.get("description") or "").strip(),
                    difficulty=difficulty,
                    is_featured=bool(item.get("is_featured", False)),
                )
                created_sets += 1

            for exercise_index, exercise in enumerate(exercises, start=1):
                if not isinstance(exercise, dict):
                    raise ValidationError(f"{title} ichidagi {exercise_index}-exercise dict emas.")

                prompt = (exercise.get("prompt") or "").strip()
                answer_mode = (exercise.get("answer_mode") or "choice").strip() or "choice"
                if not prompt:
                    raise ValidationError(f"{title} ichidagi {exercise_index}-exercise uchun prompt majburiy.")
                if answer_mode not in {"choice", "input"}:
                    raise ValidationError(f"{title} ichidagi {exercise_index}-exercise uchun answer_mode choice/input bo'lishi kerak.")

                practice_exercise = PracticeExercise.objects.create(
                    subject=subject,
                    practice_set=practice_set,
                    title=(exercise.get("title") or "").strip(),
                    source_book=(exercise.get("source_book") or item.get("source_book") or "").strip(),
                    topic=(exercise.get("topic") or item.get("topic") or "").strip(),
                    prompt=prompt,
                    answer_mode=answer_mode,
                    correct_text=(exercise.get("correct_text") or "").strip(),
                    explanation=(exercise.get("explanation") or "").strip(),
                    difficulty=normalize_difficulty_label((exercise.get("difficulty") or difficulty).strip() or difficulty),
                    is_featured=bool(exercise.get("is_featured", False)),
                )
                created_exercises += 1

                if answer_mode == "choice":
                    choices = exercise.get("choices") or []
                    if not choices:
                        raise ValidationError(f"{title} ichidagi {exercise_index}-exercise uchun choices majburiy.")

                    if isinstance(choices, dict):
                        correct_option = (exercise.get("correct_option") or "").strip().upper()
                        if correct_option not in choices:
                            raise ValidationError(f"{title} ichidagi {exercise_index}-exercise uchun correct_option topilmadi.")
                        iterable_choices = [
                            {"text": str(choice_text).strip(), "is_correct": str(choice_key).strip().upper() == correct_option}
                            for choice_key, choice_text in choices.items()
                        ]
                    else:
                        iterable_choices = choices

                    if len(iterable_choices) < 2:
                        raise ValidationError(f"{title} ichidagi {exercise_index}-exercise uchun kamida 2 ta variant kerak.")

                    has_correct = False
                    for choice in iterable_choices:
                        if not isinstance(choice, dict):
                            raise ValidationError(f"{title} ichidagi {exercise_index}-exercise varianti dict emas.")
                        text = (choice.get("text") or "").strip()
                        is_correct = bool(choice.get("is_correct", False))
                        if not text:
                            raise ValidationError(f"{title} ichidagi {exercise_index}-exercise variant matni bo'sh.")
                        has_correct = has_correct or is_correct
                        PracticeChoice.objects.create(
                            exercise=practice_exercise,
                            text=text,
                            is_correct=is_correct,
                        )
                        created_choices += 1

                    if not has_correct:
                        raise ValidationError(f"{title} ichidagi {exercise_index}-exercise uchun to'g'ri variant belgilanmagan.")
                else:
                    if not practice_exercise.correct_text:
                        raise ValidationError(f"{title} ichidagi {exercise_index}-input exercise uchun correct_text majburiy.")

    return {
        "subject": subject,
        "created_sets": created_sets,
        "updated_sets": updated_sets,
        "created_exercises": created_exercises,
        "created_choices": created_choices,
    }


def get_active_subscription_ids(user):
    return [item["subject_id"] for item in get_user_subject_access_rows(user, active_only=True)]


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
    ensure_profile_referral_code(profile, save=True)
    normalize_referral_wallet(profile, save=True)
    return profile


def get_effective_subject_level(user: User, subject_id: int | None = None, profile: Profile | None = None):
    if not subject_id:
        summary = get_user_stat_summary(user)
        return get_subject_level_info(summary.best_test_score)["label"]

    subject_best_score = (
        UserSubjectStat.objects.filter(user=user, subject_id=subject_id)
        .values_list("best_score", flat=True)
        .first()
    )
    return get_subject_level_info(subject_best_score or 0)["label"]


def get_safe_profile_photo_url(profile):
    photo = getattr(profile, "photo", None)
    if not photo:
        return ""
    try:
        return photo.url
    except Exception:
        return ""


def sidebar_context(user):
    profile = get_or_sync_profile(user)
    return {
        "profile": profile,
        "profile_photo_url": get_safe_profile_photo_url(profile),
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
    summary = get_user_stat_summary(user)

    return {
        "xp": summary.lifetime_xp,
        "correct_tests": summary.total_correct_test_answers,
        "correct_practice": summary.total_correct_practice_answers,
        "tests_xp": summary.test_xp_total,
        "practice_xp": summary.practice_xp_total,
        "grammar_xp": summary.grammar_xp_total,
        "essay_xp": summary.essay_xp_total,
        "grammar_completed": summary.total_grammar_lessons_completed,
        "essay_completed": summary.total_essay_topics_completed,
    }
