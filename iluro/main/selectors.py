from django.contrib.auth.models import User
from django.db import OperationalError, ProgrammingError
from django.db.models import Count, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    Book,
    GRADE_CHOICES,
    PracticeSet,
    PracticeSetAttempt,
    Question,
    Subject,
    SubjectSectionEntry,
    Subscription,
    Test,
    UserAnswer,
    UserStatSummary,
    UserSubjectStat,
    UserPracticeAttempt,
    UserTest,
)
from .services import (
    filter_by_allowed_level,
    get_active_subscription_ids,
    get_effective_subject_level,
    get_user_stat_summary,
    get_user_subject_access_rows,
)
from .utils import normalize_difficulty_label


LANGUAGE_BOOK_GENRE_FILTERS = [
    ("roman", "Romanlar"),
    ("qissa", "Qissalar"),
    ("drama", "Dramalar"),
    ("hikoya", "Hikoyalar"),
    ("sher", "She'rlar"),
]

LANGUAGE_PROBLEM_FILTERS = [
    ("all", "Barchasi"),
    ("grammar", "Grammatika"),
    ("literature", "Adabiyot"),
]

LITERATURE_KEYWORDS = (
    "adabiyot",
    "roman",
    "qissa",
    "hikoya",
    "she'r",
    "sher",
    "drama",
    "doston",
    "g'azal",
    "gazal",
    "ruboiy",
    "masal",
    "asar",
    "muallif",
    "obraz",
    "qahramon",
)


def is_language_subject(subject_or_name):
    subject_name = getattr(subject_or_name, "name", subject_or_name) or ""
    lowered = subject_name.lower()
    return "ona tili" in lowered or "adab" in lowered


def get_book_filter_config(subject):
    if is_language_subject(subject):
        return {
            "title": "Janr bo'yicha",
            "choices": LANGUAGE_BOOK_GENRE_FILTERS,
        }
    return {
        "title": "Sinf bo'yicha",
        "choices": GRADE_CHOICES,
    }


def get_language_problem_filter_config():
    return {
        "title": "Yo'nalish bo'yicha",
        "choices": LANGUAGE_PROBLEM_FILTERS,
    }


def _build_literature_q(fields):
    query = Q()
    for field in fields:
        for keyword in LITERATURE_KEYWORDS:
            query |= Q(**{f"{field}__icontains": keyword})
    return query


def apply_language_problem_filter(queryset, subject, selected_filter, fields):
    if not is_language_subject(subject):
        return queryset

    selected_filter = (selected_filter or "all").strip()
    if selected_filter == "all":
        return queryset

    literature_q = _build_literature_q(fields)
    if selected_filter == "literature":
        return queryset.filter(literature_q)
    if selected_filter == "grammar":
        return queryset.exclude(literature_q)
    return queryset


def get_book_bucket_label(book):
    raw_value = (book.grade or "").strip()
    if not raw_value:
        return ""

    if is_language_subject(book.subject):
        genre_map = dict(LANGUAGE_BOOK_GENRE_FILTERS)
        return genre_map.get(raw_value, "Boshqalar")

    grade_map = dict(GRADE_CHOICES)
    return grade_map.get(raw_value, raw_value)


def apply_book_filter(queryset, subject, selected_filter):
    selected_filter = (selected_filter or "").strip()
    if not selected_filter:
        return queryset

    if selected_filter == "other":
        if is_language_subject(subject):
            allowed_values = [value for value, _ in LANGUAGE_BOOK_GENRE_FILTERS]
            return queryset.exclude(grade__in=allowed_values)
        return queryset.filter(grade="")

    if is_language_subject(subject):
        allowed_values = {value for value, _ in LANGUAGE_BOOK_GENRE_FILTERS}
        if selected_filter in allowed_values:
            return queryset.filter(grade=selected_filter)
        return queryset.none()

    allowed_grades = {value for value, _ in GRADE_CHOICES}
    if selected_filter in allowed_grades:
        return queryset.filter(grade=selected_filter)
    return queryset.none()


def get_dashboard_subject_cards(user):
    subscribed_subject_ids = set(get_active_subscription_ids(user))
    subject_queryset = Subject.objects.all().annotate(test_count=Count("test"))
    subjects = []

    for subject in subject_queryset:
        subject_name_lower = subject.name.lower()
        if "ona tili" in subject_name_lower or "adab" in subject_name_lower:
            meta = "Matn, grammatika va AI yordamida esse ustida ishlash"
        elif "tarix" in subject_name_lower:
            meta = "Tarixiy jarayonlar, sanalar va manbalar tahlili"
        elif "matem" in subject_name_lower:
            meta = "Masala, mantiq va tezkor ishlash ritmi"
        else:
            meta = "Milliy sertifikatga mos tayyorlov oqimi"

        subjects.append(
            {
                "name": subject.name,
                "status": "Faol tayyorlov" if subject.id in subscribed_subject_ids else "Mavjud yo'nalish",
                "meta": meta,
                "test_count": subject.test_count,
                "is_owned": subject.id in subscribed_subject_ids,
                "id": subject.id,
            }
        )

    return subjects


def get_subject_books(subject, grade=None, limit=12):
    base_queryset = Book.objects.filter(subject=subject).order_by("-is_featured", "-created_at")
    base_queryset = apply_book_filter(base_queryset, subject, grade)

    try:
        books_queryset = base_queryset.annotate(viewer_count=Coalesce(Sum("views__view_count"), Value(0)))
        books = list(books_queryset[:limit])
    except (ProgrammingError, OperationalError):
        books = list(base_queryset[:limit])
        for book in books:
            book.viewer_count = 0

    for book in books:
        book.bucket_label = get_book_bucket_label(book)
    return books


def get_subject_tests(user, subject, profile_level, limit=6, category_filter="all", content_filter="all"):
    tests_queryset = Test.objects.filter(subject=subject)
    if category_filter in {"general", "terms", "years"}:
        tests_queryset = tests_queryset.filter(category=category_filter)
    tests_queryset = apply_language_problem_filter(tests_queryset, subject, content_filter, ["title"])
    tests = list(
        filter_by_allowed_level(tests_queryset, "difficulty", profile_level)
        .annotate(question_count=Count("question"))
        .order_by("-created_at")[:limit]
    )
    test_attempt_stats = {
        row["test_id"]: row
        for row in (
            UserTest.objects.filter(user=user, test__subject=subject)
            .values("test_id")
            .annotate(
                attempts=Count("id"),
                best_score=Max("score"),
                last_score=Max("score"),
            )
        )
    }
    for test in tests:
        test.display_difficulty = normalize_difficulty_label(test.difficulty)
        test.display_category = dict(Test._meta.get_field("category").choices).get(test.category, "Umumiy")
        attempt_data = test_attempt_stats.get(test.id, {})
        test.attempts = attempt_data.get("attempts", 0)
        test.best_score = attempt_data.get("best_score")
        test.last_score = attempt_data.get("last_score")
    return tests


def get_subject_practice_sets(user, subject, profile_level, limit=12, content_filter="all"):
    practice_queryset = PracticeSet.objects.filter(subject=subject).annotate(exercise_count=Count("exercises"))
    practice_queryset = apply_language_problem_filter(
        practice_queryset,
        subject,
        content_filter,
        ["title", "topic", "description", "source_book"],
    )
    practice_sets = list(
        filter_by_allowed_level(
            practice_queryset,
            "difficulty",
            profile_level,
        )
        .order_by("-is_featured", "-created_at")[:limit]
    )
    practice_set_attempt_rows = (
        PracticeSetAttempt.objects.filter(user=user, practice_set__subject=subject)
        .select_related("practice_set")
        .order_by("-created_at")
    )
    practice_set_attempt_map = {}
    for attempt in practice_set_attempt_rows:
        summary = practice_set_attempt_map.setdefault(
            attempt.practice_set_id,
            {
                "attempts": 0,
                "last_score": attempt.score,
                "best_score": attempt.score,
            },
        )
        summary["attempts"] += 1
        summary["best_score"] = max(summary["best_score"], attempt.score)
    for practice_set in practice_sets:
        summary = practice_set_attempt_map.get(practice_set.id, {})
        practice_set.attempts = summary.get("attempts", 0)
        practice_set.last_score = summary.get("last_score")
        practice_set.best_score = summary.get("best_score")
    return practice_sets


def get_tests_listing(user, profile_level):
    subscribed_subject_ids = get_active_subscription_ids(user)
    test_queryset = (
        filter_by_allowed_level(Test.objects.select_related("subject"), "difficulty", profile_level)
        .annotate(question_count=Count("question"))
        .order_by("-created_at")
    )
    if not subscribed_subject_ids:
        test_queryset = test_queryset.none()
    else:
        test_queryset = test_queryset.filter(subject_id__in=subscribed_subject_ids)

    return [
        {
            "id": test.id,
            "title": test.title,
            "subject": test.subject.name,
            "difficulty": normalize_difficulty_label(test.difficulty),
            "duration": test.duration,
            "question_count": test.question_count,
        }
        for test in test_queryset
    ]


def get_ranking_queryset(subject_filter="", tests_filter="all"):
    users = User.objects.select_related("profile", "stat_summary")

    if subject_filter.isdigit():
        users = users.annotate(
            effective_xp=Coalesce(Max("subject_stats__xp", filter=Q(subject_stats__subject_id=subject_filter)), Value(0)),
            best_score=Coalesce(Max("subject_stats__best_score", filter=Q(subject_stats__subject_id=subject_filter)), Value(0)),
            total_tests=Coalesce(Max("subject_stats__tests_taken", filter=Q(subject_stats__subject_id=subject_filter)), Value(0)),
        )
    else:
        users = users.annotate(
            effective_xp=Coalesce("stat_summary__lifetime_xp", Value(0)),
            best_score=Coalesce("stat_summary__best_test_score", Value(0)),
            total_tests=Coalesce("stat_summary__lifetime_test_count", Value(0)),
        )

    if tests_filter == "1_4":
        users = users.filter(total_tests__gte=1, total_tests__lte=4)
    elif tests_filter == "5_9":
        users = users.filter(total_tests__gte=5, total_tests__lte=9)
    elif tests_filter == "10_plus":
        users = users.filter(total_tests__gte=10)

    return users.order_by("-effective_xp", "-total_tests", "-best_score", "username")[:50]


def get_latest_dashboard_resources():
    latest_test = Test.objects.select_related("subject").order_by("-created_at").first()
    featured_book = Book.objects.select_related("subject").order_by("-is_featured", "-created_at").first()
    return latest_test, featured_book


def get_subject_peer_subjects(user, current_subject_id):
    active_subject_ids = set(get_active_subscription_ids(user))
    return [
        {
            "id": item.id,
            "name": item.name,
            "is_owned": item.id in active_subject_ids,
            "is_current": item.id == current_subject_id,
        }
        for item in Subject.objects.exclude(id=current_subject_id).order_by("name")[:2]
    ]


def get_user_subject_best_score(user, subject):
    return (
        UserTest.objects.filter(user=user, test__subject=subject)
        .aggregate(best_score=Max("score"))
        .get("best_score")
    ) or 0


def get_formula_entries(subject, formula_query="", formula_filter="all"):
    formulas_queryset = SubjectSectionEntry.objects.filter(subject=subject, section_key="formulas").order_by(
        "created_at", "id"
    )
    if formula_query:
        formulas_queryset = formulas_queryset.filter(
            Q(title__icontains=formula_query)
            | Q(summary__icontains=formula_query)
            | Q(body__icontains=formula_query)
            | Q(usage_note__icontains=formula_query)
        )
    if formula_filter == "featured":
        formulas_queryset = formulas_queryset.filter(is_featured=True)
    return list(formulas_queryset)


def get_user_profile_summary(user, current_level_label):
    subscriptions = get_user_subject_access_rows(user, active_only=False)

    subject_statuses = []
    active_count = 0
    subject_stats_map = {
        item.subject_id: item
        for item in UserSubjectStat.objects.filter(user=user).select_related("subject")
    }
    for subscription in subscriptions:
        is_active = subscription["end_at"] >= timezone.now()
        if is_active:
            active_count += 1
        subject_stat = subject_stats_map.get(subscription["subject_id"])
        subject_statuses.append(
            {
                "subject": subscription["subject"].name,
                "expires_at": subscription["end_at"],
                "is_active": is_active,
                "level": get_effective_subject_level(user, subject_id=subscription["subject_id"]),
                "score": subject_stat.best_score if subject_stat else 0,
            }
        )

    rank_users = (
        User.objects.select_related("profile", "stat_summary")
        .annotate(
            effective_xp=Coalesce("stat_summary__lifetime_xp", Value(0)),
            best_score=Coalesce("stat_summary__best_test_score", Value(0)),
            total_tests=Coalesce("stat_summary__lifetime_test_count", Value(0)),
        )
        .order_by("-effective_xp", "-best_score", "-total_tests", "username")
    )
    rank_position = next(
        (index for index, ranked_user in enumerate(rank_users, start=1) if ranked_user.id == user.id),
        None,
    )
    stat_summary = get_user_stat_summary(user)
    total_tests = stat_summary.lifetime_test_count
    purchased_subject_names = [item["subject"].name for item in subscriptions]

    return {
        "subject_statuses": subject_statuses,
        "rank_position": rank_position,
        "total_tests": total_tests,
        "purchased_subject_names": purchased_subject_names,
        "active_subject_count": active_count,
    }


def get_statistics_payload(user, profile_xp, current_level_label):
    active_subject_ids = set(get_active_subscription_ids(user))
    stat_summary = get_user_stat_summary(user)
    subject_stats_map = {
        item.subject_id: item
        for item in UserSubjectStat.objects.filter(user=user, subject_id__in=active_subject_ids)
    }
    user_tests = UserTest.objects.filter(user=user).select_related("test", "test__subject")

    subject_rows = []
    for subject in Subject.objects.filter(id__in=active_subject_ids).annotate(test_count=Count("test")).order_by("name"):
        subject_stat = subject_stats_map.get(subject.id)
        subject_rows.append(
            {
                "name": subject.name,
                "is_owned": subject.id in active_subject_ids,
                "attempts": subject_stat.tests_taken if subject_stat else 0,
                "best_score": subject_stat.best_score if subject_stat else 0,
                "level": get_effective_subject_level(user, subject_id=subject.id),
                "progress_percent": subject_stat.best_score if subject_stat else 0,
                "test_count": subject.test_count,
            }
        )

    recent_attempts = [
        {
            "subject": item.test.subject.name,
            "title": item.test.title,
            "score": item.score,
            "correct_count": item.correct_count,
            "finished_at": item.finished_at,
        }
        for item in user_tests.order_by("-finished_at")[:10]
    ]

    stats = [
        {"label": "Jami urinish", "value": stat_summary.lifetime_test_count, "hint": "Ishlangan testlar soni"},
        {"label": "Eng yaxshi natija", "value": f"{stat_summary.best_test_score}%", "hint": "100 ballik foiz tizimi bo'yicha"},
        {"label": "To'g'ri javoblar", "value": stat_summary.total_correct_answers, "hint": "Test va mashqlar bo'yicha"},
        {"label": "XP", "value": stat_summary.lifetime_xp, "hint": "Umumiy tajriba ochkolari"},
    ]

    return {
        "stats": stats,
        "subject_rows": subject_rows,
        "recent_attempts": recent_attempts,
    }


def get_test_answer_review(user, test):
    questions = list(
        Question.objects.filter(test=test)
        .prefetch_related("choice_set")
        .order_by("id")
    )
    user_answers = {
        answer.question_id: answer
        for answer in UserAnswer.objects.select_related("selected_choice").filter(
            user=user,
            question__test=test,
        )
    }
    answer_review = []
    for question in questions:
        correct_choice = next((choice for choice in question.choice_set.all() if choice.is_correct), None)
        user_answer = user_answers.get(question.id)
        answer_review.append(
            {
                "question": question.text,
                "selected": user_answer.selected_choice.text if user_answer and user_answer.selected_choice else "Javob tanlanmagan",
                "correct": correct_choice.text if correct_choice else "To'g'ri javob belgilanmagan",
                "is_correct": bool(user_answer and user_answer.is_correct),
            }
        )
    return answer_review


def get_practice_review_items(practice_session):
    answers = list(
        UserPracticeAttempt.objects.filter(practice_session=practice_session)
        .select_related("exercise", "selected_choice")
        .prefetch_related("exercise__choices")
        .order_by("exercise_id")
    )
    review_items = []
    for answer in answers:
        correct_choice = None
        if answer.exercise.answer_mode == "choice":
            correct_choice = answer.exercise.choices.filter(is_correct=True).first()
        review_items.append(
            {
                "title": answer.exercise.title,
                "prompt": answer.exercise.prompt,
                "is_correct": answer.is_correct,
                "selected": answer.selected_choice.text if answer.selected_choice else (answer.answer_text or "Javob kiritilmagan"),
                "correct": correct_choice.text if correct_choice else (answer.exercise.correct_text or "Ko'rsatilmagan"),
                "explanation": answer.exercise.explanation,
            }
        )
    return review_items
