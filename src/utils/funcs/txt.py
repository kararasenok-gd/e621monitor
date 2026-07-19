import re


def pluralize(count: int, one: str, few: str, many: str, other: str | None = None) -> str:
    """
    Russian pluralization rules.
    one:  21, 31, 101 ...
    few:  2-4, 22-24 ...
    many: 5-20, 25-30 ...
    other: fallback (defaults to many)
    """
    if other is None:
        other = many

    mod10 = abs(count) % 10
    mod100 = abs(count) % 100

    if 11 <= mod100 <= 14:
        return other
    if mod10 == 1:
        return one
    if 2 <= mod10 <= 4:
        return few
    return other

def clear_hashtags(text: str) -> str:
    return re.sub(r"\W", "_", text, flags=re.UNICODE)
