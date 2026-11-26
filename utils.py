"""Shared constants and presentation helpers for SpendWise."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

# Category names are stored in SQLite exactly as the keys below.
CATEGORIES: dict[str, dict[str, str]] = {
    "Food": {"icon": "cat-food", "color": "#fbbf24"},
    "Transportation": {"icon": "cat-transportation", "color": "#38bdf8"},
    "Shopping": {"icon": "cat-shopping", "color": "#a78bfa"},
    "Education": {"icon": "cat-education", "color": "#2dd4bf"},
    "Entertainment": {"icon": "cat-entertainment", "color": "#f472b6"},
    "Healthcare": {"icon": "cat-healthcare", "color": "#fb7185"},
    "Bills & Utilities": {"icon": "cat-bills", "color": "#60a5fa"},
    "Other": {"icon": "cat-other", "color": "#94a3b8"},
}

CATEGORY_NAMES = tuple(CATEGORIES)
MONTH_NAMES = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
MONTH_SHORT = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
MAX_AMOUNT = Decimal("10000000.00")  # ₹1 crore


def _group_indian(digits: str) -> str:
    """Group digits the Indian way: 12,34,567."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def format_inr(value, compact: bool = False) -> str:
    """Format a number as Indian rupees, e.g. ₹12,34,567.50."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0

    sign = "-" if amount < 0 else ""
    amount = abs(amount)

    if compact:
        if amount >= 1_00_00_000:
            text = f"{amount / 1_00_00_000:.1f}Cr"
        elif amount >= 1_00_000:
            text = f"{amount / 1_00_000:.1f}L"
        elif amount >= 1_000:
            text = f"{amount / 1_000:.1f}k"
        else:
            text = f"{amount:.0f}"
        text = text.replace(".0Cr", "Cr").replace(".0L", "L").replace(".0k", "k")
        return f"{sign}₹{text}"

    has_paise = round(amount % 1, 2) != 0
    digits = _group_indian(f"{amount:.2f}".split(".")[0]) if has_paise else _group_indian(f"{amount:.0f}")
    if has_paise:
        fraction = f"{amount:.2f}".split(".")[1]
        return f"{sign}₹{digits}.{fraction}"
    return f"{sign}₹{digits}"


def format_percent(value, decimals: int = 1) -> str:
    """Format a percentage, trimming a trailing .0."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0%"
    text = f"{number:.{decimals}f}"
    if text.endswith(".0"):
        text = text[:-2]
    return f"{text}%"


def percent_change(current: float, previous: float) -> float | None:
    """Return percentage change, or None when there is no baseline."""
    if not previous:
        return None
    return (current - previous) / previous * 100


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return the first day of the month and the first day of the next month."""
    start = date(year, month, 1)
    next_year, next_month = shift_month(year, month, 1)
    return start, date(next_year, next_month, 1)


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def parse_month(value: str | None) -> tuple[int, int] | None:
    """Parse a YYYY-MM query value, returning None when invalid."""
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except (TypeError, ValueError):
        return None
    if not 2000 <= parsed.year <= 2100:
        return None
    return parsed.year, parsed.month


def month_label(year: int, month: int, short: bool = False) -> str:
    name = MONTH_SHORT[month - 1] if short else MONTH_NAMES[month - 1]
    return f"{name} {year}"


def month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def friendly_date(value, today: date | None = None) -> str:
    parsed = as_date(value)
    if parsed is None:
        return "—"
    today = today or date.today()
    if parsed == today:
        return "Today"
    if (today - parsed).days == 1:
        return "Yesterday"
    return f"{parsed.day} {MONTH_SHORT[parsed.month - 1]} {parsed.year}"


def short_date(value) -> str:
    parsed = as_date(value)
    if parsed is None:
        return "—"
    return f"{parsed.day} {MONTH_SHORT[parsed.month - 1]} {parsed.year}"


def full_date(value) -> str:
    parsed = as_date(value)
    if parsed is None:
        return "—"
    return f"{parsed.strftime('%A')}, {parsed.day} {MONTH_NAMES[parsed.month - 1]} {parsed.year}"


def format_datetime(value) -> str:
    if not value:
        return "—"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(str(value), fmt)
            return f"{parsed.day} {MONTH_SHORT[parsed.month - 1]} {parsed.year}, {parsed.strftime('%I:%M %p')}"
        except (TypeError, ValueError):
            continue
    return str(value)


def expense_title(expense: dict) -> str:
    """Return the description, falling back to the category for blank ones."""
    description = (expense.get("description") or "").strip()
    if description:
        return description
    return expense.get("category") or "Expense"


def donut_gradient(categories: list[dict]) -> str:
    """Build a conic-gradient string from category totals."""
    total = sum(float(row.get("total", 0)) for row in categories)
    if total <= 0:
        return "conic-gradient(#1e2835 0% 100%)"

    stops: list[str] = []
    cursor = 0.0
    for index, row in enumerate(categories):
        color = CATEGORIES.get(row.get("category", ""), {}).get("color", "#94a3b8")
        end = 100.0 if index == len(categories) - 1 else cursor + (float(row["total"]) / total * 100)
        stops.append(f"{color} {cursor:.2f}% {end:.2f}%")
        cursor = end
    return f"conic-gradient({', '.join(stops)})"
