from __future__ import annotations

from datetime import date

from utils import (
    CATEGORIES,
    donut_gradient,
    expense_title,
    format_datetime,
    format_inr,
    format_percent,
    friendly_date,
    month_bounds,
    percent_change,
    shift_month,
)


def test_categories_are_complete():
    assert len(CATEGORIES) == 8
    assert "Bills & Utilities" in CATEGORIES
    for meta in CATEGORIES.values():
        assert meta["color"].startswith("#")
        assert meta["icon"].startswith("cat-")


def test_indian_currency_formatting():
    assert format_inr(0) == "₹0"
    assert format_inr(999) == "₹999"
    assert format_inr(1000) == "₹1,000"
    assert format_inr(100000) == "₹1,00,000"
    assert format_inr(1234567.5) == "₹12,34,567.50"
    assert format_inr(1234567) == "₹12,34,567"
    assert format_inr(-150.25) == "-₹150.25"


def test_compact_currency_formatting():
    assert format_inr(950, compact=True) == "₹950"
    assert format_inr(12500, compact=True) == "₹12.5k"
    assert format_inr(125000, compact=True) == "₹1.2L"
    assert format_inr(12500000, compact=True) == "₹1.2Cr"


def test_percent_formatting_and_change():
    assert format_percent(12.345) == "12.3%"
    assert format_percent(50.0) == "50%"
    assert percent_change(120, 100) == 20
    assert percent_change(80, 100) == -20
    assert percent_change(100, 0) is None


def test_month_math():
    assert shift_month(2026, 1, -1) == (2025, 12)
    assert shift_month(2026, 12, 1) == (2027, 1)
    start, end = month_bounds(2024, 2)
    assert start == date(2024, 2, 1)
    assert end == date(2024, 3, 1)


def test_friendly_dates():
    today = date(2026, 11, 26)
    assert friendly_date(today, today) == "Today"
    assert friendly_date(date(2026, 11, 25), today) == "Yesterday"
    assert friendly_date("2026-11-01", today) == "1 Nov 2026"


def test_datetime_formatting():
    assert format_datetime("2026-11-26 09:05:00") == "26 Nov 2026, 09:05 AM"
    assert format_datetime(None) == "—"


def test_expense_title_falls_back_to_category():
    assert expense_title({"description": "Lunch", "category": "Food"}) == "Lunch"
    assert expense_title({"description": "", "category": "Food"}) == "Food"
    assert expense_title({"description": "   ", "category": "Healthcare"}) == "Healthcare"
    assert expense_title({"description": None, "category": "Shopping"}) == "Shopping"


def test_donut_gradient_uses_category_colors():
    categories = [
        {"category": "Food", "total": 75},
        {"category": "Shopping", "total": 25},
    ]
    gradient = donut_gradient(categories)
    assert gradient.startswith("conic-gradient(")
    assert CATEGORIES["Food"]["color"] in gradient
    assert CATEGORIES["Shopping"]["color"] in gradient
    assert "100.00%" in gradient
    assert "#1e2835" in donut_gradient([])
