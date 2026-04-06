import re

from django import template


register = template.Library()


_NUMBERED_SPLIT_RE = re.compile(r"(?=(?:^|\s)(\d+\)))")


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


@register.filter
def leading_text(value):
    text = _normalize_spaces(value)
    if not text:
        return ""
    match = re.search(r"(?:^|\s)\d+\)", text)
    if not match:
        return text
    return text[: match.start()].strip(" :;-")


@register.filter
def numbered_items(value):
    text = _normalize_spaces(value)
    if not text:
        return []
    match = re.search(r"(?:^|\s)\d+\)", text)
    if not match:
        return []
    numbered_part = text[match.start():].strip()
    parts = _NUMBERED_SPLIT_RE.split(numbered_part)
    items = []
    pending_number = None
    for part in parts:
        cleaned = _normalize_spaces(part)
        if not cleaned:
            continue
        if re.fullmatch(r"\d+\)", cleaned):
            pending_number = cleaned
            continue
        if pending_number:
            items.append(f"{pending_number} {cleaned}".strip())
            pending_number = None
        else:
            items.append(cleaned)
    return items
