LEVEL_MAX_SCORE = 50

LEVEL_RULES = [
    {"label": "S", "min": 0, "max": 8},
    {"label": "S+", "min": 9, "max": 16},
    {"label": "B", "min": 17, "max": 24},
    {"label": "B+", "min": 25, "max": 32},
    {"label": "A", "min": 33, "max": 40},
    {"label": "A+", "min": 41, "max": LEVEL_MAX_SCORE},
]


def clamp_score(score: int | None, max_score: int = LEVEL_MAX_SCORE) -> int:
    if score is None:
        return 0
    return max(0, min(score, max_score))


def get_level_info(score: int | None, max_score: int = LEVEL_MAX_SCORE) -> dict:
    normalized_score = clamp_score(score, max_score)

    for rule in LEVEL_RULES:
        if rule["min"] <= normalized_score <= rule["max"]:
            return {
                "label": rule["label"],
                "score": normalized_score,
                "max_score": max_score,
                "range_text": f'{rule["min"]}-{rule["max"]} ball',
            }

    fallback = LEVEL_RULES[-1]
    return {
        "label": fallback["label"],
        "score": normalized_score,
        "max_score": max_score,
        "range_text": f'{fallback["min"]}-{fallback["max"]} ball',
    }
