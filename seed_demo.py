"""Populate SpendWise with realistic demo data.

Run `python seed_demo.py` only when you want sample transactions for a demo.
The script refuses to touch a database that already contains expenses.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from app import create_app
from database import count_expenses, create_expense, get_db
from utils import shift_month

# (category, description, amount) for the current month, placed on recent days.
CURRENT_MONTH = [
    ("Food", "Team lunch at the office cafe", 640),
    ("Transportation", "Metro card recharge", 500),
    ("Shopping", "Running shoes", 2499),
    ("Bills & Utilities", "Electricity bill", 1840),
    ("Food", "Groceries for the week", 2260),
    ("Entertainment", "Movie tickets", 640),
    ("Healthcare", "Pharmacy refill", 320),
    ("Education", "Online Python course", 1299),
    ("Other", "Birthday gift for cousin", 850),
    ("Food", "Coffee and sandwich", 260),
]

# Recurring sample data for earlier months.
PAST_MONTHS = [
    [
        ("Bills & Utilities", "Monthly internet bill", 999),
        ("Food", "Dinner with friends", 1450),
        ("Transportation", "Auto ride to college", 180),
        ("Shopping", "Winter jacket", 3299),
        ("Education", "Reference textbook", 780),
        ("Entertainment", "Concert ticket", 1200),
        ("Healthcare", "Doctor consultation", 600),
    ],
    [
        ("Food", "Groceries and household items", 2850),
        ("Transportation", "Bus pass", 750),
        ("Bills & Utilities", "Mobile recharge", 399),
        ("Shopping", "Backpack", 1899),
        ("Other", "Stationery and printouts", 240),
        ("Entertainment", "Streaming subscription", 499),
    ],
    [
        ("Food", "Weekend brunch", 920),
        ("Transportation", "Fuel top-up", 1100),
        ("Education", "Lab manual", 450),
        ("Healthcare", "Vitamins", 540),
        ("Shopping", "Headphones", 2199),
        ("Bills & Utilities", "Water bill", 320),
    ],
    [
        ("Food", "Family dinner", 2100),
        ("Transportation", "Cab to railway station", 420),
        ("Entertainment", "Cricket match tickets", 1500),
        ("Other", "Charity donation", 500),
        ("Shopping", "Phone case", 399),
        ("Bills & Utilities", "Electricity bill", 1730),
    ],
]


def _clamped(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(max(day, 1), last_day))


def seed() -> None:
    app = create_app()
    with app.app_context():
        if count_expenses() > 0:
            print(
                "Database already contains expenses. Nothing was changed.\n"
                "To create a fresh demo database, delete database/spendwise.db first."
            )
            return

        today = date.today()
        rows: list[tuple[str, str, float, str]] = []

        # Current month: spread the sample expenses over the last few days.
        for index, (category, description, amount) in enumerate(CURRENT_MONTH):
            offset = index * 2
            transaction_date = today - timedelta(days=offset)
            if transaction_date.month != today.month:
                break
            rows.append((category, description, float(amount), transaction_date.isoformat()))

        # A couple of expenses dated today for a lively dashboard.
        rows.append(("Food", "Morning filter coffee", 120.0, today.isoformat()))
        rows.append(("Transportation", "Auto fare", 95.0, today.isoformat()))

        # Previous months.
        for month_offset, entries in enumerate(PAST_MONTHS, start=1):
            year, month = shift_month(today.year, today.month, -month_offset)
            days = [4, 9, 14, 19, 24, 27, 28][: len(entries)]
            for day, (category, description, amount) in zip(days, entries):
                rows.append(
                    (
                        category,
                        description,
                        float(amount),
                        _clamped(year, month, day).isoformat(),
                    )
                )

        for category, description, amount, transaction_date in rows:
            create_expense(
                amount=amount,
                category=category,
                description=description,
                transaction_date=transaction_date,
            )

        db = get_db()
        row = db.execute("SELECT COUNT(*) AS c, SUM(amount) AS t FROM expenses").fetchone()
        print(f"Added {row['c']} demo expenses worth INR {row['t']:,.2f}.")
        print(f"Database: {app.config['DATABASE']}")
        print("Start the app with: python app.py")


if __name__ == "__main__":
    seed()
