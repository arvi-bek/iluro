from django.db.models import Case, IntegerField, Value, When

XP_PER_CORRECT_TEST_ANSWER = 6
XP_PER_CORRECT_PRACTICE_ANSWER = 5

DIFFICULTY_ALIAS_MAP = {
    "s": "C",
    "s+": "C+",
    "c": "C",
    "c+": "C+",
    "b": "B",
    "b+": "B+",
    "a": "A",
    "a+": "A+",
    "easy": "C",
    "medium": "B",
    "hard": "A",
    "very hard": "A+",
}

LEVEL_ORDER = ["C", "C+", "B", "B+", "A", "A+"]
DIFFICULTY_ORDER_MAP = {label: index for index, label in enumerate(LEVEL_ORDER)}

XP_LEVEL_RULES = [
    {"label": "✨ Yangi User", "min_xp": 0, "max_xp": 200},
    {"label": "🎓 O'quvchi", "min_xp": 200, "max_xp": 500},
    {"label": "🔥 Izlanuvchi", "min_xp": 500, "max_xp": 750},
    {"label": "B+", "min_xp": 750, "max_xp": 1000},
    {"label": "A", "min_xp": 1000, "max_xp": 1500},
    {"label": "A+", "min_xp": 1500, "max_xp": 2000},
]

SCORE_LEVEL_RULES = [
    {"label": "C", "min_score": 0, "max_score": 16},
    {"label": "C+", "min_score": 17, "max_score": 32},
    {"label": "B", "min_score": 33, "max_score": 48},
    {"label": "B+", "min_score": 49, "max_score": 64},
    {"label": "A", "min_score": 65, "max_score": 80},
    {"label": "A+", "min_score": 81, "max_score": 100},
]

# Rebalanced XP economy. These later definitions intentionally override the
# legacy values above so existing imports can keep working.
TEST_BASE_XP_PER_CORRECT = 2
PRACTICE_SET_BASE_XP_PER_CORRECT = 1

SINGLE_PRACTICE_XP_BY_DIFFICULTY = {
    "C": 2,
    "C+": 2,
    "B": 3,
    "B+": 3,
    "A": 4,
    "A+": 5,
}

TEST_DIFFICULTY_XP_BONUS = {
    "C": 0,
    "C+": 2,
    "B": 4,
    "B+": 6,
    "A": 8,
    "A+": 10,
}

PRACTICE_SET_DIFFICULTY_XP_BONUS = {
    "C": 0,
    "C+": 1,
    "B": 2,
    "B+": 3,
    "A": 4,
    "A+": 5,
}

GRAMMAR_COMPLETION_XP_BY_DIFFICULTY = {
    "C": 6,
    "C+": 7,
    "B": 8,
    "B+": 9,
    "A": 10,
    "A+": 11,
}

ESSAY_TOPIC_XP_BY_DIFFICULTY = {
    "C": 8,
    "C+": 10,
    "B": 12,
    "B+": 14,
    "A": 16,
    "A+": 18,
}

XP_LEVEL_RULES = [
    {"label": "✨ Yangi User", "min_xp": 0, "max_xp": 249},
    {"label": "🎓 O'quvchi", "min_xp": 250, "max_xp": 649},
    {"label": "🔥 Izlanuvchi", "min_xp": 650, "max_xp": 1299},
    {"label": "🧭 Barqaror", "min_xp": 1300, "max_xp": 2199},
    {"label": "⚡ Kuchli", "min_xp": 2200, "max_xp": 3499},
    {"label": "👑 Ustoz", "min_xp": 3500, "max_xp": None},
]


def clamp_xp(xp: int | None) -> int:
    if xp is None:
        return 0
    return max(0, xp)


def get_level_min_xp(level_label: str | None) -> int:
    normalized_label = (level_label or "").strip()
    for rule in XP_LEVEL_RULES:
        if rule["label"] == normalized_label:
            return rule["min_xp"]
    return 0


def get_level_choices() -> list[tuple[str, str]]:
    return [(rule["label"], rule["label"]) for rule in XP_LEVEL_RULES]


def normalize_difficulty_label(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return DIFFICULTY_ALIAS_MAP.get(normalized, (value or "B").strip().upper())


def get_difficulty_rank(value: str | None) -> int:
    normalized = normalize_difficulty_label(value)
    return DIFFICULTY_ORDER_MAP.get(normalized, len(LEVEL_ORDER))


def build_difficulty_order_expression(field_name: str = "difficulty"):
    return Case(
        *[
            When(**{field_name: label}, then=Value(index))
            for index, label in enumerate(LEVEL_ORDER)
        ],
        default=Value(len(LEVEL_ORDER)),
        output_field=IntegerField(),
    )


def calculate_score_percent(correct_count: int | None, total_count: int | None) -> int:
    normalized_total = max(int(total_count or 0), 0)
    if normalized_total == 0:
        return 0
    normalized_correct = max(0, min(int(correct_count or 0), normalized_total))
    return round((normalized_correct / normalized_total) * 100)


def _get_test_accuracy_bonus(score_percent: int) -> int:
    if score_percent >= 100:
        return 20
    if score_percent >= 95:
        return 16
    if score_percent >= 85:
        return 12
    if score_percent >= 70:
        return 8
    if score_percent >= 55:
        return 4
    return 0


def _get_practice_accuracy_bonus(score_percent: int) -> int:
    if score_percent >= 100:
        return 10
    if score_percent >= 95:
        return 8
    if score_percent >= 85:
        return 6
    if score_percent >= 70:
        return 4
    if score_percent >= 55:
        return 2
    return 0


def calculate_test_xp(correct_count: int | None, total_count: int | None, difficulty: str | None) -> int:
    normalized_correct = max(int(correct_count or 0), 0)
    score_percent = calculate_score_percent(normalized_correct, total_count)
    normalized_difficulty = normalize_difficulty_label(difficulty)

    xp = normalized_correct * TEST_BASE_XP_PER_CORRECT
    if score_percent >= 40 and normalized_correct > 0:
        xp += 6
    xp += _get_test_accuracy_bonus(score_percent)
    if score_percent >= 55:
        xp += TEST_DIFFICULTY_XP_BONUS.get(normalized_difficulty, 0)
    return xp


def calculate_practice_set_xp(correct_count: int | None, total_count: int | None, difficulty: str | None) -> int:
    normalized_correct = max(int(correct_count or 0), 0)
    score_percent = calculate_score_percent(normalized_correct, total_count)
    normalized_difficulty = normalize_difficulty_label(difficulty)

    xp = normalized_correct * PRACTICE_SET_BASE_XP_PER_CORRECT
    if score_percent >= 40 and normalized_correct > 0:
        xp += 4
    xp += _get_practice_accuracy_bonus(score_percent)
    if score_percent >= 55:
        xp += PRACTICE_SET_DIFFICULTY_XP_BONUS.get(normalized_difficulty, 0)
    return xp


def calculate_single_practice_xp(is_correct: bool, difficulty: str | None) -> int:
    if not is_correct:
        return 0
    normalized_difficulty = normalize_difficulty_label(difficulty)
    return SINGLE_PRACTICE_XP_BY_DIFFICULTY.get(normalized_difficulty, 2)


def calculate_grammar_lesson_xp(
    best_score: int | None,
    difficulty: str | None,
    is_completed: bool,
    has_attempt: bool,
) -> int:
    if not has_attempt:
        return 0

    normalized_score = max(0, min(int(best_score or 0), 100))
    normalized_difficulty = normalize_difficulty_label(difficulty)
    xp = 2

    if normalized_score >= 100:
        xp += 10
    elif normalized_score >= 90:
        xp += 8
    elif normalized_score >= 80:
        xp += 6
    elif normalized_score >= 65:
        xp += 4
    elif normalized_score >= 50:
        xp += 2

    if is_completed:
        xp += GRAMMAR_COMPLETION_XP_BY_DIFFICULTY.get(normalized_difficulty, 6)

    return xp


def calculate_essay_topic_xp(difficulty: str | None, is_completed: bool, is_featured: bool = False) -> int:
    if not is_completed:
        return 0
    normalized_difficulty = normalize_difficulty_label(difficulty)
    xp = ESSAY_TOPIC_XP_BY_DIFFICULTY.get(normalized_difficulty, 8)
    if is_featured:
        xp += 2
    return xp


def get_allowed_level_labels(current_level: str | None) -> list[str]:
    normalized_level = normalize_difficulty_label(current_level or "C")
    if normalized_level not in LEVEL_ORDER:
        normalized_level = "C"
    current_index = LEVEL_ORDER.index(normalized_level)
    return LEVEL_ORDER[: current_index + 1]


def get_level_info(xp: int | None) -> dict:
    normalized_xp = clamp_xp(xp)

    for index, rule in enumerate(XP_LEVEL_RULES):
        max_xp = rule["max_xp"]
        if max_xp is None or rule["min_xp"] <= normalized_xp <= max_xp:
            next_rule = XP_LEVEL_RULES[index + 1] if index + 1 < len(XP_LEVEL_RULES) else None
            next_threshold = next_rule["min_xp"] if next_rule else None
            if next_threshold is None:
                progress_percent = 100
                xp_to_next = 0
            else:
                span = max(1, next_threshold - rule["min_xp"])
                progress_percent = int(((normalized_xp - rule["min_xp"]) / span) * 100)
                xp_to_next = max(0, next_threshold - normalized_xp)

            range_text = (
                f'{rule["min_xp"]}+ XP'
                if max_xp is None
                else f'{rule["min_xp"]}-{max_xp} XP'
            )
            return {
                "label": rule["label"],
                "xp": normalized_xp,
                "range_text": range_text,
                "next_threshold": next_threshold,
                "next_label": next_rule["label"] if next_rule else rule["label"],
                "xp_to_next": xp_to_next,
                "progress_percent": max(0, min(progress_percent, 100)),
            }

    fallback = XP_LEVEL_RULES[-1]
    return {
        "label": fallback["label"],
        "xp": normalized_xp,
        "range_text": f'{fallback["min_xp"]}+ XP',
        "next_threshold": None,
        "next_label": fallback["label"],
        "xp_to_next": 0,
        "progress_percent": 100,
    }


def get_subject_level_info(score: int | None) -> dict:
    normalized_score = max(0, min(score or 0, 100))
    for rule in SCORE_LEVEL_RULES:
        if rule["min_score"] <= normalized_score <= rule["max_score"]:
            return {
                "label": rule["label"],
                "score": normalized_score,
                "range_text": f'{rule["min_score"]}-{rule["max_score"]}%',
                "progress_percent": normalized_score,
            }

    fallback = SCORE_LEVEL_RULES[-1]
    return {
        "label": fallback["label"],
        "score": normalized_score,
        "range_text": f'{fallback["min_score"]}-{fallback["max_score"]}%',
        "progress_percent": normalized_score,
    }
