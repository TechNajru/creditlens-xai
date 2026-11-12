from .categorizer import CREDIT_CATEGORIES, DEBIT_CATEGORIES


def allowed_categories(direction: str) -> list[str]:
    return CREDIT_CATEGORIES if direction == "credit" else DEBIT_CATEGORIES
