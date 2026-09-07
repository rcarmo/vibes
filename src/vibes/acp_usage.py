"""Validate optional ACP usage without inferring context from billed tokens."""
import math
import re

TOKEN_FIELDS = ("inputTokens", "outputTokens", "totalTokens", "thoughtTokens", "cachedReadTokens", "cachedWriteTokens")


def token_count(value):
    return value if type(value) is int and 0 <= value <= 2**53 - 1 else None


def context_update(update):
    used, size = token_count(update.get("used")), token_count(update.get("size"))
    cost = update.get("cost")
    valid_cost = None
    if isinstance(cost, dict):
        amount, currency = cost.get("amount"), cost.get("currency")
        if (type(amount) in (int, float) and 0 <= amount <= 1e15 and math.isfinite(amount)
                and isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency)):
            valid_cost = {"amount": amount, "currency": currency}
    return {
        "tokens": used if size and used is not None else None,
        "contextWindow": size if size and used is not None else None,
        "percent": round(100 * used / size, 1) if size and used is not None else None,
        "cost": valid_cost,
    }


def turn_usage(value):
    if not isinstance(value, dict):
        return None
    result = {key: value[key] for key in TOKEN_FIELDS if token_count(value.get(key)) is not None}
    return result or None
