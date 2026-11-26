"""SQLite data access for SpendWise.

All SQL lives here so Flask routes stay focused on HTTP handling.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from flask import current_app, g

from utils import (
    CATEGORY_NAMES,
    MONTH_NAMES,
    MONTH_SHORT,
    month_bounds,
    percent_change,
    shift_month,
)

_CATEGORY_SQL = ", ".join(f"'{name}'" for name in CATEGORY_NAMES)


def _expenses_table_sql(if_not_exists: bool = False) -> str:
    guard = "IF NOT EXISTS " if if_not_exists else ""
    return f"""
CREATE TABLE {guard}expenses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    amount           REAL    NOT NULL CHECK (amount > 0),
    category         TEXT    NOT NULL CHECK (category IN ({_CATEGORY_SQL})),
    description      TEXT    NOT NULL DEFAULT '',
    transaction_date TEXT    NOT NULL CHECK (length(transaction_date) = 10),
    created_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""


SCHEMA = _expenses_table_sql(if_not_exists=True) + """
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (transaction_date);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses (category);
"""

_LEGACY_DESCRIPTION_CONSTRAINT = "length(trim(description)) > 0"


def get_db() -> sqlite3.Connection:
    """Return the request-scoped SQLite connection."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _migrate_optional_description(db: sqlite3.Connection) -> None:
    """Rebuild old tables that enforced a non-empty description.

    SQLite cannot drop a CHECK constraint in place, so the table is rebuilt
    atomically while keeping every row and its original id.
    """
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'expenses'"
    ).fetchone()
    if row is None:
        return
    if _LEGACY_DESCRIPTION_CONSTRAINT not in (row["sql"] or "").lower():
        return

    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("ALTER TABLE expenses RENAME TO expenses_legacy")
        db.execute(_expenses_table_sql())
        db.execute(
            """
            INSERT INTO expenses
                (id, amount, category, description, transaction_date, created_at, updated_at)
            SELECT id, amount, category,
                   CASE WHEN length(trim(description)) > 0 THEN description ELSE '' END,
                   transaction_date, created_at, updated_at
            FROM expenses_legacy
            """
        )
        db.execute("DROP TABLE expenses_legacy")
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses (transaction_date)"
        )
        db.execute(
            "CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses (category)"
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


def init_db() -> None:
    """Create tables and indexes when they do not exist."""
    db = get_db()
    _migrate_optional_description(db)
    db.executescript(SCHEMA)
    db.commit()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)


def _dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


def _range_sum(db: sqlite3.Connection, start: date, end: date) -> tuple[float, int]:
    row = db.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
        FROM expenses
        WHERE transaction_date >= ? AND transaction_date < ?
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    return float(row["total"]), int(row["count"])


def count_expenses() -> int:
    row = get_db().execute("SELECT COUNT(*) AS count FROM expenses").fetchone()
    return int(row["count"])


def get_expense(expense_id: int) -> dict | None:
    row = get_db().execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    return dict(row) if row else None


def create_expense(amount: float, category: str, description: str, transaction_date: str) -> int:
    db = get_db()
    with db:
        cursor = db.execute(
            """
            INSERT INTO expenses (amount, category, description, transaction_date)
            VALUES (?, ?, ?, ?)
            """,
            (amount, category, description, transaction_date),
        )
    return int(cursor.lastrowid)


def update_expense(
    expense_id: int, amount: float, category: str, description: str, transaction_date: str
) -> bool:
    db = get_db()
    with db:
        cursor = db.execute(
            """
            UPDATE expenses
            SET amount = ?, category = ?, description = ?, transaction_date = ?,
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (amount, category, description, transaction_date, expense_id),
        )
    return cursor.rowcount > 0


def delete_expense(expense_id: int) -> bool:
    db = get_db()
    with db:
        cursor = db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    return cursor.rowcount > 0


def get_expenses(filters: dict | None = None) -> list[dict]:
    """Return expenses matching search, category, date range and sort filters."""
    filters = filters or {}
    sql = "SELECT * FROM expenses WHERE 1 = 1"
    params: list = []

    search = (filters.get("q") or "").strip()
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        sql += " AND description LIKE ? ESCAPE '\\'"
        params.append(f"%{escaped}%")

    category = filters.get("category")
    if category:
        sql += " AND category = ?"
        params.append(category)

    date_from = filters.get("date_from")
    if date_from:
        sql += " AND transaction_date >= ?"
        params.append(date_from)

    date_to = filters.get("date_to")
    if date_to:
        sql += " AND transaction_date <= ?"
        params.append(date_to)

    if filters.get("sort") == "oldest":
        sql += " ORDER BY transaction_date ASC, id ASC"
    else:
        sql += " ORDER BY transaction_date DESC, id DESC"

    return _dicts(get_db().execute(sql, params).fetchall())


def get_category_totals(start: date, end: date) -> list[dict]:
    rows = get_db().execute(
        """
        SELECT category, SUM(amount) AS total, COUNT(*) AS count
        FROM expenses
        WHERE transaction_date >= ? AND transaction_date < ?
        GROUP BY category
        ORDER BY total DESC, category ASC
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()

    categories = _dicts(rows)
    overall = sum(row["total"] for row in categories)
    for row in categories:
        row["total"] = float(row["total"])
        row["percent"] = (row["total"] / overall * 100) if overall else 0.0
    return categories


def get_monthly_series(end_year: int, end_month: int, count: int = 6) -> list[dict]:
    """Return the last `count` months (oldest first) with totals."""
    start_year, start_month = shift_month(end_year, end_month, -(count - 1))
    start = date(start_year, start_month, 1)
    _unused, end = month_bounds(end_year, end_month)

    rows = get_db().execute(
        """
        SELECT substr(transaction_date, 1, 7) AS ym,
               SUM(amount) AS total,
               COUNT(*) AS count
        FROM expenses
        WHERE transaction_date >= ? AND transaction_date < ?
        GROUP BY ym
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    lookup = {row["ym"]: row for row in rows}

    series: list[dict] = []
    year, month = start_year, start_month
    for index in range(count):
        key = f"{year:04d}-{month:02d}"
        row = lookup.get(key)
        series.append(
            {
                "key": key,
                "year": year,
                "month": month,
                "label": MONTH_SHORT[month - 1],
                "full_label": f"{MONTH_NAMES[month - 1]} {year}",
                "total": float(row["total"]) if row else 0.0,
                "count": int(row["count"]) if row else 0,
                "highlight": index == count - 1,
            }
        )
        year, month = shift_month(year, month, 1)
    return series


def get_dashboard_data(today: date | None = None) -> dict:
    today = today or date.today()
    db = get_db()
    start, end = month_bounds(today.year, today.month)
    prev_start, prev_end = month_bounds(*shift_month(today.year, today.month, -1))

    month_total, month_count = _range_sum(db, start, end)
    today_total, today_count = _range_sum(db, today, today + timedelta(days=1))
    previous_total, _ = _range_sum(db, prev_start, prev_end)
    categories = get_category_totals(start, end)
    trend = get_monthly_series(today.year, today.month, 6)

    recent = _dicts(
        db.execute(
            """
            SELECT * FROM expenses
            ORDER BY transaction_date DESC, id DESC
            LIMIT 6
            """
        ).fetchall()
    )
    largest = db.execute(
        """
        SELECT * FROM expenses
        WHERE transaction_date >= ? AND transaction_date < ?
        ORDER BY amount DESC, transaction_date DESC, id DESC
        LIMIT 1
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    busiest = db.execute(
        """
        SELECT transaction_date, SUM(amount) AS total, COUNT(*) AS count
        FROM expenses
        WHERE transaction_date >= ? AND transaction_date < ?
        GROUP BY transaction_date
        ORDER BY total DESC, transaction_date DESC
        LIMIT 1
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    active_days_row = db.execute(
        """
        SELECT COUNT(DISTINCT transaction_date) AS days
        FROM expenses
        WHERE transaction_date >= ? AND transaction_date < ?
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchone()

    days_elapsed = today.day
    return {
        "month_start": start,
        "month_total": month_total,
        "month_count": month_count,
        "today_total": today_total,
        "today_count": today_count,
        "previous_month_total": previous_total,
        "month_change": percent_change(month_total, previous_total),
        "avg_daily": month_total / days_elapsed if days_elapsed else 0.0,
        "days_elapsed": days_elapsed,
        "categories": categories,
        "recent": recent,
        "trend": trend,
        "largest": dict(largest) if largest else None,
        "busiest": dict(busiest) if busiest else None,
        "active_days": int(active_days_row["days"]) if active_days_row else 0,
        "trend_total": sum(item["total"] for item in trend),
    }


def get_analytics_data(year: int, month: int, today: date | None = None) -> dict:
    today = today or date.today()
    db = get_db()
    start, end = month_bounds(year, month)
    prev_start, prev_end = month_bounds(*shift_month(year, month, -1))

    total, count = _range_sum(db, start, end)
    previous_total, previous_count = _range_sum(db, prev_start, prev_end)
    categories = get_category_totals(start, end)

    days_in_month = (end - start).days
    if (year, month) == (today.year, today.month):
        days_counted = today.day
    else:
        days_counted = days_in_month

    active_days_row = db.execute(
        """
        SELECT COUNT(DISTINCT transaction_date) AS days
        FROM expenses
        WHERE transaction_date >= ? AND transaction_date < ?
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchone()
    busiest = db.execute(
        """
        SELECT transaction_date, SUM(amount) AS total, COUNT(*) AS count
        FROM expenses
        WHERE transaction_date >= ? AND transaction_date < ?
        GROUP BY transaction_date
        ORDER BY total DESC, transaction_date DESC
        LIMIT 1
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchone()

    prev_year, prev_month = shift_month(year, month, -1)
    return {
        "year": year,
        "month": month,
        "month_key": f"{year:04d}-{month:02d}",
        "month_label": f"{MONTH_NAMES[month - 1]} {year}",
        "start": start,
        "end": end,
        "total": total,
        "count": count,
        "avg_daily": total / days_counted if days_counted else 0.0,
        "active_days": int(active_days_row["days"]) if active_days_row else 0,
        "days_in_month": days_in_month,
        "categories": categories,
        "trend": get_monthly_series(year, month, 6),
        "previous_total": previous_total,
        "previous_count": previous_count,
        "previous_label": f"{MONTH_NAMES[prev_month - 1]} {prev_year}",
        "previous_month_key": f"{prev_year:04d}-{prev_month:02d}",
        "change": percent_change(total, previous_total),
        "busiest": dict(busiest) if busiest else None,
    }
