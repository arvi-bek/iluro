import random
import re

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import OperationalError, ProgrammingError
from django.db.models import Count, Max, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import (
    Book,
    GRADE_CHOICES,
    PracticeExercise,
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
    get_active_subscription_ids,
    get_effective_subject_level,
    get_user_stat_summary,
    get_user_subject_access_rows,
)
from .utils import build_difficulty_order_expression, normalize_difficulty_label


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

HISTORY_GRADE_PATTERN = re.compile(r"(?<!\d)(5|6|7|8|9|10|11)\s*[- ]?\s*sinf", re.IGNORECASE)
HISTORY_GAME_CACHE_SECONDS = 900
HISTORY_BATTLE_QUESTION_TARGET = 30
IMLO_KEYWORDS = (
    "imlo",
    "imloviy",
    "to'g'ri yoz",
    "to‘g‘ri yoz",
    "yozma savodxonlik",
    "orfograf",
)
IMLO_DUEL_QUESTION_TARGET = 30
LANGUAGE_DUEL_SUBJECT_OPTIONS = [
    {"value": "language", "label": "Ona tili"},
    {"value": "literature", "label": "Adabiyot"},
]


def is_language_subject(subject_or_name):
    subject_name = getattr(subject_or_name, "name", subject_or_name) or ""
    lowered = subject_name.lower()
    return "ona tili" in lowered or "adab" in lowered


def extract_grade_label(title):
    match = HISTORY_GRADE_PATTERN.search(title or "")
    return match.group(1) if match else ""


def extract_history_grade_label(title):
    return extract_grade_label(title)


def extract_history_grade_from_parts(*parts):
    for part in parts:
        grade = extract_grade_label(part)
        if grade:
            return grade
    return ""


def _top_up_history_question_pool(question_pool, limit):
    if not question_pool or len(question_pool) >= limit:
        return question_pool[:limit]

    expanded = list(question_pool)
    while len(expanded) < limit:
        candidates = [
            item
            for item in question_pool
            if not expanded or item["text"] != expanded[-1]["text"]
        ] or question_pool
        expanded.append(random.choice(candidates).copy())
    return expanded[:limit]


def _get_history_subject():
    return Subject.objects.filter(name__icontains="tarix").order_by("name").first()


def get_history_game_grade_options():
    cache_key = "history-game-grade-options"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    history_subject = _get_history_subject()
    if not history_subject:
        cache.set(cache_key, [], HISTORY_GAME_CACHE_SECONDS)
        return []

    tests = list(
        Test.objects.filter(subject=history_subject)
        .annotate(question_count=Count("question"))
        .values("title", "question_count")
    )
    exercises = list(
        PracticeExercise.objects.filter(subject=history_subject, answer_mode="choice")
        .annotate(choice_count=Count("choices"))
        .values("title", "topic", "source_book", "choice_count")
    )
    buckets = {}
    for test in tests:
        grade = extract_history_grade_label(test["title"])
        if not grade:
            continue
        bucket = buckets.setdefault(
            grade,
            {
                "value": grade,
                "label": f"{grade}-sinf",
                "question_count": 0,
                "test_count": 0,
            },
        )
        bucket["question_count"] += test["question_count"]
        bucket["test_count"] += 1

    for exercise in exercises:
        grade = extract_history_grade_from_parts(
            exercise["topic"],
            exercise["title"],
            exercise["source_book"],
        )
        if not grade or exercise["choice_count"] < 4:
            continue
        bucket = buckets.setdefault(
            grade,
            {
                "value": grade,
                "label": f"{grade}-sinf",
                "question_count": 0,
                "test_count": 0,
            },
        )
        bucket["question_count"] += 1

    options = [
        buckets[key]
        for key in sorted(buckets.keys(), key=lambda item: int(item))
        if buckets[key]["question_count"] > 0
    ]
    cache.set(cache_key, options, HISTORY_GAME_CACHE_SECONDS)
    return options


def get_history_battle_questions(grade="", limit=8):
    history_subject = _get_history_subject()
    if not history_subject:
        return []

    selected_grade = str(grade or "").strip()
    tests = list(Test.objects.filter(subject=history_subject).prefetch_related("question_set__choice_set"))
    exercises = list(
        PracticeExercise.objects.filter(subject=history_subject, answer_mode="choice").prefetch_related("choices")
    )
    if selected_grade:
        tests = [test for test in tests if extract_history_grade_label(test.title) == selected_grade]
        exercises = [
            exercise
            for exercise in exercises
            if extract_history_grade_from_parts(exercise.topic, exercise.title, exercise.source_book) == selected_grade
        ]

    question_pool = []
    for test in tests:
        for question in test.question_set.all():
            choices = list(question.choice_set.all())
            correct_choices = [choice for choice in choices if choice.is_correct]
            wrong_choices = [choice for choice in choices if not choice.is_correct]
            if len(correct_choices) != 1 or len(wrong_choices) < 3:
                continue

            selected_choices = [correct_choices[0], *random.sample(wrong_choices, 3)]
            random.shuffle(selected_choices)
            correct_index = next(
                (index for index, choice in enumerate(selected_choices) if choice.is_correct),
                0,
            )
            question_pool.append(
                {
                    "text": question.text.strip(),
                    "options": [choice.text.strip() for choice in selected_choices],
                    "correct_index": correct_index,
                    "difficulty": normalize_difficulty_label(question.difficulty),
                    "source_title": test.title,
                    "grade": extract_history_grade_label(test.title),
                }
            )

    for exercise in exercises:
        choices = list(exercise.choices.all())
        correct_choices = [choice for choice in choices if choice.is_correct]
        wrong_choices = [choice for choice in choices if not choice.is_correct]
        if len(correct_choices) != 1 or len(wrong_choices) < 3:
            continue

        selected_choices = [correct_choices[0], *random.sample(wrong_choices, 3)]
        random.shuffle(selected_choices)
        correct_index = next(
            (index for index, choice in enumerate(selected_choices) if choice.is_correct),
            0,
        )
        source_title = exercise.topic or exercise.title or "Tarix mashqi"
        grade = extract_history_grade_from_parts(exercise.topic, exercise.title, exercise.source_book)
        question_pool.append(
            {
                "text": exercise.prompt.strip(),
                "options": [choice.text.strip() for choice in selected_choices],
                "correct_index": correct_index,
                "difficulty": normalize_difficulty_label(exercise.difficulty),
                "source_title": source_title,
                "grade": grade,
            }
        )

    random.shuffle(question_pool)
    return _top_up_history_question_pool(question_pool, limit)


def _get_language_subject():
    return Subject.objects.filter(Q(name__icontains="ona tili") | Q(name__icontains="adab")).order_by("name").first()


def get_language_duel_subject_options():
    return list(LANGUAGE_DUEL_SUBJECT_OPTIONS)


def _language_content_haystack(*parts):
    return " ".join(part or "" for part in parts).lower()


def _is_literature_content(*parts):
    haystack = _language_content_haystack(*parts)
    return any(keyword in haystack for keyword in LITERATURE_KEYWORDS)


def _is_imlo_content(*parts):
    haystack = _language_content_haystack(*parts)
    return any(keyword in haystack for keyword in IMLO_KEYWORDS)


def _matches_language_duel_subject(subject_kind, *parts):
    subject_kind = (subject_kind or "language").strip() or "language"
    is_literature = _is_literature_content(*parts)
    is_imlo = _is_imlo_content(*parts)
    if subject_kind == "literature":
        return is_literature
    if subject_kind == "language":
        return not is_literature and not is_imlo
    return not is_literature and not is_imlo


def extract_imlo_grade_from_parts(*parts):
    for part in parts:
        grade = extract_grade_label(part)
        if grade:
            return grade
    return ""


def _get_imlo_grade_label(exercise):
    return extract_imlo_grade_from_parts(
        getattr(exercise, "title", ""),
        getattr(exercise, "topic", ""),
        getattr(exercise, "source_book", ""),
        getattr(getattr(exercise, "practice_set", None), "title", ""),
        getattr(getattr(exercise, "practice_set", None), "topic", ""),
        getattr(getattr(exercise, "practice_set", None), "source_book", ""),
    )


def _get_language_game_grade_label(*parts):
    return extract_imlo_grade_from_parts(*parts)


def get_imlo_duel_grade_options(subject_kind="language"):
    language_subject = _get_language_subject()
    if not language_subject:
        return []

    subject_kind = (subject_kind or "language").strip() or "language"
    tests = list(
        Test.objects.filter(subject=language_subject)
        .annotate(question_count=Count("question"))
        .values("title", "question_count")
    )
    exercises = (
        PracticeExercise.objects.filter(subject=language_subject, answer_mode="choice").select_related("practice_set")
        .annotate(choice_count=Count("choices"))
        .order_by("-created_at")
    )
    buckets = {}
    fallback_count = 0

    for test in tests:
        if not test["question_count"]:
            continue
        if not _matches_language_duel_subject(subject_kind, test["title"]):
            continue
        grade = _get_language_game_grade_label(test["title"])
        if not grade:
            fallback_count += test["question_count"]
            continue
        bucket = buckets.setdefault(
            grade,
            {
                "value": grade,
                "label": f"{grade}-sinf",
                "question_count": 0,
                "test_count": 0,
            },
        )
        bucket["question_count"] += test["question_count"]
        bucket["test_count"] += 1

    for exercise in exercises:
        if exercise.choice_count < 4:
            continue
        if not _matches_language_duel_subject(
            subject_kind,
            exercise.title,
            exercise.topic,
            exercise.source_book,
            exercise.prompt,
            exercise.explanation,
            getattr(getattr(exercise, "practice_set", None), "title", ""),
            getattr(getattr(exercise, "practice_set", None), "topic", ""),
            getattr(getattr(exercise, "practice_set", None), "source_book", ""),
        ):
            continue
        grade = _get_imlo_grade_label(exercise)
        if not grade:
            fallback_count += 1
            continue
        bucket = buckets.setdefault(
            grade,
            {
                "value": grade,
                "label": f"{grade}-sinf",
                "question_count": 0,
                "test_count": 0,
            },
        )
        bucket["question_count"] += 1

    options = [
        buckets[key]
        for key in sorted(buckets.keys(), key=lambda item: int(item))
        if key in buckets and buckets[key]["question_count"] > 0
    ]
    if fallback_count:
        options.append(
            {
                "value": "all",
                "label": "Aralash",
                "question_count": fallback_count,
                "test_count": 0,
            }
        )
    return options


def get_imlo_duel_level_options():
    return get_imlo_duel_grade_options()


def get_imlo_duel_questions(level="", limit=8, subject_kind="language"):
    language_subject = _get_language_subject()
    if not language_subject:
        return []

    selected_level = str(level or "").strip()
    subject_kind = (subject_kind or "language").strip() or "language"

    tests = list(
        Test.objects.filter(subject=language_subject)
        .prefetch_related("question_set__choice_set")
    )
    exercises = list(
        PracticeExercise.objects.filter(subject=language_subject, answer_mode="choice")
        .select_related("practice_set")
        .prefetch_related("choices")
    )

    question_pool = []

    for test in tests:
        if not _matches_language_duel_subject(subject_kind, test.title):
            continue
        grade_label = _get_language_game_grade_label(test.title) or "all"
        if selected_level:
            if selected_level == "all" and grade_label != "all":
                continue
            if selected_level != "all" and grade_label != selected_level:
                continue

        for question in test.question_set.all():
            choices = list(question.choice_set.all())
            correct_choices = [choice for choice in choices if choice.is_correct]
            wrong_choices = [choice for choice in choices if not choice.is_correct]
            if len(correct_choices) != 1 or len(wrong_choices) < 3:
                continue

            selected_choices = [correct_choices[0], *random.sample(wrong_choices, 3)]
            random.shuffle(selected_choices)
            correct_index = next(
                (index for index, choice in enumerate(selected_choices) if choice.is_correct),
                0,
            )
            question_pool.append(
                {
                    "text": question.text.strip(),
                    "options": [choice.text.strip() for choice in selected_choices],
                    "correct_index": correct_index,
                    "difficulty": normalize_difficulty_label(question.difficulty or test.difficulty),
                    "source_title": test.title or ("Adabiyot savoli" if subject_kind == "literature" else "Ona tili savoli"),
                    "grade": grade_label,
                }
            )

    for exercise in exercises:
        if not _matches_language_duel_subject(
            subject_kind,
            exercise.title,
            exercise.topic,
            exercise.source_book,
            exercise.prompt,
            exercise.explanation,
            getattr(getattr(exercise, "practice_set", None), "title", ""),
            getattr(getattr(exercise, "practice_set", None), "topic", ""),
            getattr(getattr(exercise, "practice_set", None), "source_book", ""),
        ):
            continue
        grade_label = _get_imlo_grade_label(exercise) or "all"
        if selected_level:
            if selected_level == "all" and grade_label != "all":
                continue
            if selected_level != "all" and grade_label != selected_level:
                continue
        choices = list(exercise.choices.all())
        correct_choices = [choice for choice in choices if choice.is_correct]
        wrong_choices = [choice for choice in choices if not choice.is_correct]
        if len(correct_choices) != 1 or len(wrong_choices) < 3:
            continue

        selected_choices = [correct_choices[0], *random.sample(wrong_choices, 3)]
        random.shuffle(selected_choices)
        correct_index = next(
            (index for index, choice in enumerate(selected_choices) if choice.is_correct),
            0,
        )
        source_title = exercise.topic or exercise.title or exercise.source_book or "Imlo mashqi"
        question_pool.append(
            {
                "text": exercise.prompt.strip(),
                "options": [choice.text.strip() for choice in selected_choices],
                "correct_index": correct_index,
                "difficulty": normalize_difficulty_label(exercise.difficulty),
                "source_title": source_title,
                "grade": grade_label,
            }
        )

    random.shuffle(question_pool)
    return _top_up_history_question_pool(question_pool, limit)


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
        tests_queryset.annotate(
            question_count=Count("question"),
            difficulty_sort=build_difficulty_order_expression("difficulty"),
        )
        .order_by("difficulty_sort", "-created_at", "-id")[:limit]
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
        practice_queryset.annotate(
            difficulty_sort=build_difficulty_order_expression("difficulty"),
        )
        .order_by("difficulty_sort", "-is_featured", "-created_at", "-id")[:limit]
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
        Test.objects.select_related("subject")
        .annotate(
            question_count=Count("question"),
            difficulty_sort=build_difficulty_order_expression("difficulty"),
        )
        .order_by("difficulty_sort", "-created_at", "-id")
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


def _normalize_math_topic_label(*parts):
    for part in parts:
        normalized = " ".join((part or "").replace("_", " ").split()).strip(" -")
        if normalized:
            return normalized
    return "Aralash mavzu"


def _build_choice_question_payload(source_id, prompt, options, explanation="", detail="", prefix="quiz"):
    normalized_options = []
    correct_letter = ""
    for index, option in enumerate(options):
        letter = chr(65 + index)
        normalized_options.append(
            {
                "letter": letter,
                "text": option["text"],
                "is_correct": bool(option["is_correct"]),
            }
        )
        if option["is_correct"]:
            correct_letter = letter

    if not correct_letter:
        return None

    return {
        "id": f"{prefix}-{source_id}",
        "prompt": prompt,
        "detail": detail,
        "choices": normalized_options,
        "correct_letter": correct_letter,
        "explanation": explanation or "",
    }


def _normalize_formula_quiz_text(value, fallback=""):
    text = " ".join((value or "").split())
    return text or fallback


def _short_formula_quiz_text(value, *, limit=220, fallback=""):
    text = _normalize_formula_quiz_text(value, fallback)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _build_formula_quiz_options(pool, correct_entry, index, text_getter):
    correct_text = _normalize_formula_quiz_text(text_getter(correct_entry))
    if not correct_text:
        return []

    distractors = [item for item in pool if item.id != correct_entry.id]
    offset = index % len(distractors) if distractors else 0
    rotated = distractors[offset:] + distractors[:offset]

    option_rows = [{"text": correct_text, "is_correct": True}]
    seen = {correct_text}
    for item in rotated:
        text = _normalize_formula_quiz_text(text_getter(item))
        if not text or text in seen:
            continue
        seen.add(text)
        option_rows.append({"text": text, "is_correct": False})
        if len(option_rows) == 4:
            break

    if len(option_rows) < 2:
        return []

    option_rows = option_rows[:4]
    random.shuffle(option_rows)
    return option_rows


def _build_formula_quiz_question(entry, pool, index, question_type):
    title = _normalize_formula_quiz_text(entry.title, "Formula mavzusi")
    summary = _normalize_formula_quiz_text(entry.summary, "")
    body = _normalize_formula_quiz_text(entry.body, "")
    usage = _normalize_formula_quiz_text(entry.usage_note, "")
    context_line = usage or summary or "Bu formula matematikaning asosiy tayanchlaridan biri."

    if question_type == "name_from_formula" and body:
        options = _build_formula_quiz_options(pool, entry, index, lambda item: item.title)
        payload = _build_choice_question_payload(
            source_id=f"{entry.id}-name-{index}",
            prefix="formula",
            prompt="Quyidagi formulani nomini toping.",
            detail=body,
            explanation=f"{title}. {context_line}".strip(),
            options=options,
        )
    elif question_type == "usage_from_formula" and body and context_line:
        options = _build_formula_quiz_options(pool, entry, index, lambda item: item.usage_note or item.summary)
        payload = _build_choice_question_payload(
            source_id=f"{entry.id}-usage-{index}",
            prefix="formula",
            prompt="Quyidagi formula asosan qayerda ishlatiladi?",
            detail=body,
            explanation=f"{title}. {context_line}".strip(),
            options=options,
        )
    elif question_type == "formula_from_name" and title and body:
        descriptor = summary or usage or "Quyidagi mavzuga mos formulani toping."
        options = _build_formula_quiz_options(pool, entry, index, lambda item: item.body)
        payload = _build_choice_question_payload(
            source_id=f"{entry.id}-body-{index}",
            prefix="formula",
            prompt=f'"{title}" formulasiga mos yozuvni toping.',
            detail=_short_formula_quiz_text(descriptor, limit=180),
            explanation=f"{title}. {context_line}".strip(),
            options=options,
        )
    elif question_type == "name_from_usage" and context_line:
        options = _build_formula_quiz_options(pool, entry, index, lambda item: item.title)
        payload = _build_choice_question_payload(
            source_id=f"{entry.id}-context-{index}",
            prefix="formula",
            prompt="Quyidagi qo'llanish tavsifi qaysi formula mavzusiga tegishli?",
            detail=_short_formula_quiz_text(context_line, limit=220),
            explanation=f"{title}. {body or context_line}".strip(),
            options=options,
        )
    else:
        payload = None

    if payload:
        payload["answer_title"] = title
        payload["question_type"] = question_type
        payload["question_type_label"] = {
            "name_from_formula": "Nomini toping",
            "usage_from_formula": "Qayerda ishlatiladi",
            "formula_from_name": "Formulani toping",
            "name_from_usage": "Mavzuni toping",
        }.get(question_type, "Formula savoli")
    return payload


def get_math_formula_quiz_payload(subject, *, max_questions=10):
    entries = get_formula_entries(subject)
    if len(entries) < 2:
        return []

    pool = entries[: max(max_questions + 6, 6)]
    questions = []
    question_types = (
        "name_from_formula",
        "usage_from_formula",
        "formula_from_name",
        "name_from_usage",
    )
    safety_limit = max_questions * 4
    cursor = 0
    while len(questions) < max_questions and cursor < safety_limit:
        entry = pool[cursor % len(pool)]
        question_type = question_types[cursor % len(question_types)]
        payload = _build_formula_quiz_question(entry, pool, cursor, question_type)
        if payload and not any(item["id"] == payload["id"] for item in questions):
            questions.append(payload)
        cursor += 1

    return questions


def get_math_topic_quiz_groups(subject, profile_level, *, max_questions=8):
    exercises = (
        PracticeExercise.objects.filter(subject=subject, answer_mode="choice")
        .select_related("practice_set")
        .prefetch_related("choices")
        .annotate(difficulty_sort=build_difficulty_order_expression("difficulty"))
        .order_by("difficulty_sort", "-is_featured", "-created_at", "-id")
    )

    grouped = {}
    for exercise in exercises:
        choice_rows = list(exercise.choices.all())
        correct_choices = [choice for choice in choice_rows if choice.is_correct]
        wrong_choices = [choice for choice in choice_rows if not choice.is_correct]
        if len(correct_choices) != 1 or len(wrong_choices) < 1:
            continue

        topic_label = _normalize_math_topic_label(
            exercise.topic,
            getattr(exercise.practice_set, "topic", ""),
            exercise.title,
            getattr(exercise.practice_set, "title", ""),
        )
        topic_key = re.sub(r"[^a-z0-9]+", "-", topic_label.lower()).strip("-") or f"topic-{exercise.id}"
        group = grouped.setdefault(
            topic_key,
            {
                "key": topic_key,
                "title": topic_label,
                "summary": getattr(exercise.practice_set, "description", "") or exercise.explanation or "",
                "difficulty": normalize_difficulty_label(exercise.difficulty),
                "question_total": 0,
                "questions": [],
                "practice_set_id": exercise.practice_set_id,
                "source_title": getattr(exercise.practice_set, "title", "") or topic_label,
                "is_featured": bool(exercise.is_featured or getattr(exercise.practice_set, "is_featured", False)),
            },
        )

        group["question_total"] += 1
        if len(group["questions"]) >= max_questions:
            continue

        option_rows = [correct_choices[0], *wrong_choices[:3]]
        random.shuffle(option_rows)
        payload = _build_choice_question_payload(
            source_id=exercise.id,
            prefix="topic",
            prompt=exercise.prompt,
            detail=exercise.title or exercise.topic or topic_label,
            explanation=exercise.explanation or "",
            options=[
                {
                    "text": choice.text,
                    "is_correct": choice.is_correct,
                }
                for choice in option_rows
            ],
        )
        if payload:
            group["questions"].append(payload)

    topic_groups = [
        {
            **group,
            "question_count": len(group["questions"]),
        }
        for group in grouped.values()
        if len(group["questions"]) >= 2
    ]
    topic_groups.sort(key=lambda item: (-int(item["is_featured"]), -item["question_total"], item["title"].lower()))
    return topic_groups


def get_user_math_mistake_items(user, subject, *, limit=12):
    items = []

    practice_attempts = (
        UserPracticeAttempt.objects.filter(user=user, exercise__subject=subject, is_correct=False)
        .select_related("exercise", "exercise__practice_set", "selected_choice")
        .prefetch_related("exercise__choices")
        .order_by("exercise_id", "-created_at", "-id")
    )
    seen_exercise_ids = set()
    for attempt in practice_attempts:
        if attempt.exercise_id in seen_exercise_ids:
            continue
        seen_exercise_ids.add(attempt.exercise_id)

        correct_choice = next((choice for choice in attempt.exercise.choices.all() if choice.is_correct), None)
        items.append(
            {
                "kind": "practice",
                "occurred_at": attempt.created_at,
                "title": attempt.exercise.title or attempt.exercise.topic or "Mashq savoli",
                "topic": _normalize_math_topic_label(
                    attempt.exercise.topic,
                    getattr(attempt.exercise.practice_set, "topic", ""),
                    getattr(attempt.exercise.practice_set, "title", ""),
                ),
                "prompt": attempt.exercise.prompt,
                "your_answer": (
                    attempt.selected_choice.text
                    if attempt.selected_choice
                    else (attempt.answer_text or "Javob kiritilmagan")
                ),
                "correct_answer": (
                    correct_choice.text
                    if correct_choice
                    else (attempt.exercise.correct_text or "To'g'ri javob belgilanmagan")
                ),
                "explanation": attempt.exercise.explanation or "",
                "retry_href": (
                    f"/practice/sets/{attempt.exercise.practice_set_id}/solve/?next=/subjects/{subject.id}/mistakes/"
                    if attempt.exercise.practice_set_id
                    else ""
                ),
                "source_label": "Mashq",
            }
        )

    test_attempts = (
        UserTest.objects.filter(user=user, test__subject=subject)
        .select_related("test")
        .order_by("-finished_at", "-started_at", "-id")
    )
    latest_wrong_answers = []
    seen_question_ids = set()
    question_ids = []
    for attempt in test_attempts:
        for answer in attempt.snapshot_json.get("answers", []):
            question_id = answer.get("question_id")
            if not question_id or question_id in seen_question_ids:
                continue
            if answer.get("is_correct"):
                continue
            seen_question_ids.add(question_id)
            latest_wrong_answers.append(
                {
                    "question_id": question_id,
                    "selected_choice_id": answer.get("selected_choice_id"),
                    "occurred_at": attempt.finished_at or attempt.started_at,
                    "test": attempt.test,
                }
            )
            question_ids.append(question_id)

    question_map = {
        question.id: question
        for question in Question.objects.filter(id__in=question_ids).select_related("test").prefetch_related("choice_set")
    }
    for answer in latest_wrong_answers:
        question = question_map.get(answer["question_id"])
        if not question:
            continue

        selected_choice = next(
            (choice for choice in question.choice_set.all() if choice.id == answer["selected_choice_id"]),
            None,
        )
        correct_choice = next((choice for choice in question.choice_set.all() if choice.is_correct), None)
        items.append(
            {
                "kind": "test",
                "occurred_at": answer["occurred_at"],
                "title": question.test.title,
                "topic": normalize_difficulty_label(question.difficulty),
                "prompt": question.text,
                "your_answer": selected_choice.text if selected_choice else "Javob tanlanmagan",
                "correct_answer": correct_choice.text if correct_choice else "To'g'ri javob belgilanmagan",
                "explanation": "",
                "retry_href": f"/tests/{question.test_id}/start/?next=/subjects/{subject.id}/mistakes/",
                "source_label": "Test",
            }
        )

    items.sort(key=lambda item: item["occurred_at"] or timezone.now(), reverse=True)
    return items[:limit]


def get_user_profile_summary(user, current_level_label):
    subscriptions = get_user_subject_access_rows(user, active_only=False)

    subject_statuses = []
    active_count = 0
    subject_stats_map = {
        item.subject_id: item
        for item in UserSubjectStat.objects.filter(user=user).select_related("subject")
    }
    for subscription in subscriptions:
        is_active = subscription["is_permanent"] or (subscription["end_at"] and subscription["end_at"] >= timezone.now())
        if is_active:
            active_count += 1
        subject_stat = subject_stats_map.get(subscription["subject_id"])
        subject_statuses.append(
            {
                "subject": subscription["subject"].name,
                "expires_at": subscription["end_at"],
                "is_permanent": subscription["is_permanent"],
                "is_active": is_active,
                "level": get_effective_subject_level(user, subject_id=subscription["subject_id"]),
                "score": subject_stat.best_score if subject_stat else 0,
                "source": subscription["source"],
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
