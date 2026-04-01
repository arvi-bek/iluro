XP_PER_TEST = 1

DIFFICULTY_ALIAS_MAP = {
    "s": "S",
    "s+": "S+",
    "b": "B",
    "b+": "B+",
    "a": "A",
    "a+": "A+",
    "easy": "S",
    "medium": "B",
    "hard": "A",
    "very hard": "A+",
}

LEVEL_ORDER = ["S", "S+", "B", "B+", "A", "A+"]

XP_LEVEL_RULES = [
    {"label": "S", "min_xp": 0, "max_xp": 99},
    {"label": "S+", "min_xp": 100, "max_xp": 249},
    {"label": "B", "min_xp": 250, "max_xp": 499},
    {"label": "B+", "min_xp": 500, "max_xp": 799},
    {"label": "A", "min_xp": 800, "max_xp": 1199},
    {"label": "A+", "min_xp": 1200, "max_xp": None},
]

SCORE_LEVEL_RULES = [
    {"label": "S", "min_score": 0, "max_score": 16},
    {"label": "S+", "min_score": 17, "max_score": 32},
    {"label": "B", "min_score": 33, "max_score": 48},
    {"label": "B+", "min_score": 49, "max_score": 64},
    {"label": "A", "min_score": 65, "max_score": 80},
    {"label": "A+", "min_score": 81, "max_score": 100},
]


def clamp_xp(xp: int | None) -> int:
    if xp is None:
        return 0
    return max(0, xp)


def normalize_difficulty_label(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return DIFFICULTY_ALIAS_MAP.get(normalized, (value or "B").strip().upper())


def get_allowed_level_labels(current_level: str | None) -> list[str]:
    normalized_level = normalize_difficulty_label(current_level or "S")
    if normalized_level not in LEVEL_ORDER:
        normalized_level = "S"
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
