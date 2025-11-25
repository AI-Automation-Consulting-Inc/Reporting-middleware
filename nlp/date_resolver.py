import re
from typing import Tuple, Dict, Any


def resolve_date_range(question: str, config: Dict[str, Any]) -> Tuple[str, bool]:
    """
    Resolve a natural-language date range in `question` to one of the
    configured `date_ranges` keys in `config`.

    Returns (date_range_key, auto_mapped)
    - date_range_key: a key from config['date_ranges']
    - auto_mapped: True if we mapped an unsupported range to the nearest allowed
      bucket (e.g. "last 5 months" -> "last_6_months"). False if question
      explicitly matched an allowed bucket.
    """
    if not question:
        # fallback to first allowed or a default
        allowed = list(config.get("date_ranges", {}).keys())
        if allowed:
            return allowed[0], False
        return ("last_12_months", False)

    q = question.lower()
    allowed = config.get("date_ranges", {})
    if not allowed:
        return ("last_12_months", False)

    # Try to match known keywords (exact keys) first (explicit phrasing).
    for key in allowed.keys():
        # match phrases like "last 6 months" to key names containing 6 or '6'
        if key.replace("_", " ") in q:
            return key, False

    # Try to detect an explicit month count: "last 5 months", "past 6 months"
    m = re.search(r"(?:last|past)\s+(\d+)\s+months?", q)
    if m:
        try:
            months = int(m.group(1))
        except ValueError:
            months = None
        if months:
            # Build a mapping of allowed key -> months equivalent (approx days/30)
            allowed_months = {}
            for k, days in allowed.items():
                try:
                    allowed_months[k] = int(round(int(days) / 30.0))
                except Exception:
                    allowed_months[k] = None
            # find best match by absolute difference in months
            best_key = None
            best_diff = None
            for k, am in allowed_months.items():
                if am is None:
                    continue
                diff = abs(am - months)
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_key = k
            if best_key:
                return best_key, True

    # No explicit match — if there's a token like "last 6" or "6 months" try to guess
    m2 = re.search(r"(\d+)\s+months?", q)
    if m2:
        try:
            months = int(m2.group(1))
        except Exception:
            months = None
        if months:
            # same mapping strategy
            allowed_months = {
                k: int(round(int(days) / 30.0))
                for k, days in allowed.items()
                if isinstance(days, (int, float, str))
            }
            best = min(allowed_months.items(), key=lambda kv: abs(kv[1] - months))
            return best[0], True

    # fallback: if only one allowed, return it
    if len(allowed) == 1:
        return next(iter(allowed.keys())), False

    # default: prefer last_6_months if present, else first allowed
    if "last_6_months" in allowed:
        return "last_6_months", False

    return next(iter(allowed.keys())), False
