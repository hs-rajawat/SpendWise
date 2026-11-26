from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

import database
from app import create_app
from database import create_expense
from utils import shift_month


def payload(**overrides):
    data = {
        "amount": "250.50",
        "category": "Food",
        "description": "Lunch with the team",
        "transaction_date": date.today().isoformat(),
    }
    data.update(overrides)
    return data


def insert(app, amount, category, description, txn_date):
    with app.app_context():
        return create_expense(
            amount=float(amount),
            category=category,
            description=description,
            transaction_date=txn_date,
        )


def previous_month_date(day=10):
    year, month = shift_month(date.today().year, date.today().month, -1)
    return date(year, month, day).isoformat()


# ---------------------------------------------------------------------------
# Creation, editing, deletion
# ---------------------------------------------------------------------------

def test_database_is_initialized(app):
    with app.app_context():
        row = database.get_db().execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'expenses'"
        ).fetchone()
        assert row is not None


def test_legacy_database_is_migrated_without_losing_records(tmp_path):
    db_path = tmp_path / "legacy-spendwise.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE expenses (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            amount           REAL    NOT NULL CHECK (amount > 0),
            category         TEXT    NOT NULL CHECK (category IN (
                'Food', 'Transportation', 'Shopping', 'Education',
                'Entertainment', 'Healthcare', 'Bills & Utilities', 'Other'
            )),
            description      TEXT    NOT NULL CHECK (length(trim(description)) > 0),
            transaction_date TEXT    NOT NULL CHECK (length(transaction_date) = 10),
            created_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
        );

        CREATE INDEX idx_expenses_date ON expenses (transaction_date);
        CREATE INDEX idx_expenses_category ON expenses (category);

        INSERT INTO expenses
            (id, amount, category, description, transaction_date, created_at, updated_at)
        VALUES
            (7, 51, 'Food', 'Legacy lunch', '2026-11-20',
             '2026-11-20 10:00:00', '2026-11-21 11:30:00');
        """
    )
    connection.commit()
    connection.close()

    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": str(db_path),
        }
    )

    with application.app_context():
        assert database.count_expenses() == 1
        expense = database.get_expense(7)
        assert expense["amount"] == 51
        assert expense["category"] == "Food"
        assert expense["description"] == "Legacy lunch"
        assert expense["transaction_date"] == "2026-11-20"
        assert expense["created_at"] == "2026-11-20 10:00:00"
        assert expense["updated_at"] == "2026-11-21 11:30:00"

        new_id = create_expense(51, "Food", "", date.today().isoformat())
        assert new_id == 8
        assert database.get_expense(new_id)["description"] == ""

        schema = database.get_db().execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'expenses'"
        ).fetchone()["sql"].lower()
        assert "length(trim(description)) > 0" not in schema

    with application.test_client() as legacy_client:
        html = legacy_client.get("/expenses/7").get_data(as_text=True)
    assert "Legacy lunch" in html
    assert "₹51" in html


def test_add_expense(client, app):
    response = client.post("/expenses/add", data=payload(), follow_redirects=True)
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    assert "Expense added successfully." in html
    assert "Lunch with the team" in html
    assert "₹250.50" in html

    with app.app_context():
        expense = database.get_expenses()[0]
    assert expense["amount"] == 250.5
    assert expense["category"] == "Food"
    assert expense["description"] == "Lunch with the team"
    assert expense["transaction_date"] == date.today().isoformat()


def test_edit_expense(client, app):
    expense_id = insert(app, 99, "Transportation", "Bus ticket", date.today().isoformat())

    edit_page = client.get(f"/expenses/{expense_id}/edit")
    assert edit_page.status_code == 200
    assert "Bus ticket" in edit_page.get_data(as_text=True)

    response = client.post(
        f"/expenses/{expense_id}/edit",
        data=payload(amount="149.25", category="Shopping", description="Updated purchase"),
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Expense updated successfully." in html
    assert "Updated purchase" in html
    assert "₹149.25" in html

    with app.app_context():
        expense = database.get_expense(expense_id)
    assert expense["amount"] == 149.25
    assert expense["category"] == "Shopping"
    assert expense["description"] == "Updated purchase"


def test_edit_expense_description_can_be_cleared(client, app):
    expense_id = insert(app, 99, "Transportation", "Bus ticket", date.today().isoformat())

    response = client.post(
        f"/expenses/{expense_id}/edit",
        data=payload(amount="99", category="Transportation", description="", transaction_date=date.today().isoformat()),
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Expense updated successfully." in html
    assert "<h2>Transportation</h2>" in html

    with app.app_context():
        assert database.get_expense(expense_id)["description"] == ""


def test_delete_expense(client, app):
    expense_id = insert(app, 499, "Entertainment", "Movie night", date.today().isoformat())

    response = client.post(f"/expenses/{expense_id}/delete", follow_redirects=True)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Expense deleted." in html

    with app.app_context():
        assert database.get_expense(expense_id) is None
        assert database.count_expenses() == 0


def test_missing_expense_returns_404(client):
    assert client.get("/expenses/9999").status_code == 404
    assert client.get("/expenses/9999/edit").status_code == 404
    assert client.post("/expenses/9999/delete").status_code == 404


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("amount", "0", "greater than zero"),
        ("amount", "-20", "greater than zero"),
        ("amount", "12.345", "two decimal places"),
        ("amount", "not-a-number", "valid amount"),
        ("category", "Groceries", "valid category"),
        ("transaction_date", (date.today() + timedelta(days=1)).isoformat(), "future"),
        ("transaction_date", "2026-02-30", "valid date"),
    ],
)
def test_invalid_expense_is_rejected(client, app, field, value, message):
    response = client.post("/expenses/add", data=payload(**{field: value}))
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert message in html
    assert "We couldn't save this expense" in html
    with app.app_context():
        assert database.count_expenses() == 0


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("amount", "Enter an amount."),
        ("category", "Choose a category."),
        ("transaction_date", "Choose a transaction date."),
    ],
)
def test_required_fields_are_rejected(client, app, field, message):
    response = client.post("/expenses/add", data=payload(**{field: ""}))
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert message in html
    assert "We couldn't save this expense" in html
    with app.app_context():
        assert database.count_expenses() == 0


@pytest.mark.parametrize("description", ["", "   ", "\t \n  "])
def test_empty_description_is_optional(client, app, description):
    response = client.post(
        "/expenses/add",
        data=payload(amount="51", category="Food", description=description),
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Expense added successfully." in html
    assert "₹51" in html
    assert "<h2>Food</h2>" in html

    with app.app_context():
        expense = database.get_expenses()[0]
        assert expense["amount"] == 51
        assert expense["category"] == "Food"
        assert expense["description"] == ""


def test_blank_description_uses_category_across_pages(client, app):
    expense_id = insert(app, 51, "Food", "", date.today().isoformat())

    dashboard = client.get("/").get_data(as_text=True)
    assert '<span class="txn-title">Food</span>' in dashboard
    assert '<span class="insight-value">Food</span>' in dashboard

    transactions = client.get("/transactions").get_data(as_text=True)
    assert '<span class="txn-title">Food</span>' in transactions
    assert 'aria-label="View Food"' in transactions

    detail = client.get(f"/expenses/{expense_id}").get_data(as_text=True)
    assert "<h2>Food</h2>" in detail
    assert 'data-confirm="Delete “Food”' in detail
    assert "<title>Food · SpendWise</title>" in detail


def test_amount_with_too_many_digits_is_rejected(client):
    response = client.post("/expenses/add", data=payload(amount="10000001"))
    assert "₹1 crore or less" in response.get_data(as_text=True)


def test_description_is_safely_escaped(client, app):
    description = "<script>alert(1)</script>"
    response = client.post(
        "/expenses/add",
        data=payload(description=description),
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# ---------------------------------------------------------------------------
# Dashboard aggregation
# ---------------------------------------------------------------------------

def test_dashboard_calculations(app):
    today = date.today()
    insert(app, 120.50, "Food", "Breakfast", today.isoformat())
    insert(app, 250, "Transportation", "Cab ride", today.isoformat())
    insert(app, 500, "Shopping", "Headphones", today.isoformat())
    insert(app, 1000, "Food", "Last month groceries", previous_month_date())

    with app.app_context():
        data = database.get_dashboard_data(today=today)

    assert data["month_total"] == pytest.approx(870.50)
    assert data["today_total"] == pytest.approx(870.50)
    assert data["month_count"] == 3
    assert data["today_count"] == 3
    assert data["avg_daily"] == pytest.approx(870.50 / today.day)
    assert data["previous_month_total"] == pytest.approx(1000)
    assert data["month_change"] == pytest.approx((870.50 - 1000) / 1000 * 100)
    assert len(data["categories"]) == 3
    percentage_total = sum(category["percent"] for category in data["categories"])
    assert percentage_total == pytest.approx(100)
    assert data["trend"][-1]["total"] == pytest.approx(870.50)
    assert data["active_days"] == 1


def test_dashboard_page_uses_database_values(client, app):
    today = date.today()
    insert(app, 120.50, "Food", "Breakfast", today.isoformat())
    insert(app, 250, "Transportation", "Cab ride", today.isoformat())

    response = client.get("/")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "₹370.50" in html
    assert "Breakfast" in html
    assert "Cab ride" in html
    assert "Category breakdown" in html
    assert "Monthly spending" in html


def test_empty_dashboard_and_empty_states(client):
    dashboard = client.get("/").get_data(as_text=True)
    assert "No transactions yet" in dashboard
    assert "₹0" in dashboard

    transactions = client.get("/transactions").get_data(as_text=True)
    assert "No transactions yet" in transactions

    filtered = client.get("/transactions?q=nothing").get_data(as_text=True)
    assert "No matching transactions" in filtered


# ---------------------------------------------------------------------------
# Search, filtering and sorting
# ---------------------------------------------------------------------------

def seed_filter_data(app):
    today = date.today()
    insert(app, 120, "Food", "Filter coffee", today.isoformat())
    insert(app, 800, "Transportation", "Airport cab", (today - timedelta(days=3)).isoformat())
    insert(app, 2500, "Shopping", "Headphones", (today - timedelta(days=10)).isoformat())
    insert(app, 900, "Food", "Pizza night", previous_month_date(15))


def test_search_by_description(client, app):
    seed_filter_data(app)
    html = client.get("/transactions?q=coffee").get_data(as_text=True)
    assert "Filter coffee" in html
    assert "Airport cab" not in html
    assert "Pizza night" not in html

    case_insensitive = client.get("/transactions?q=COFFEE").get_data(as_text=True)
    assert "Filter coffee" in case_insensitive


def test_search_escapes_like_wildcards(client, app):
    today = date.today().isoformat()
    insert(app, 40, "Food", "100% juice", today)
    insert(app, 60, "Food", "100 mango juice", today)

    html = client.get("/transactions?q=100%25").get_data(as_text=True)
    assert "100% juice" in html
    assert "100 mango juice" not in html


def test_filter_by_category(client, app):
    seed_filter_data(app)
    html = client.get("/transactions?category=Food").get_data(as_text=True)
    assert "Filter coffee" in html
    assert "Pizza night" in html
    assert "Airport cab" not in html


def test_filter_by_date_range(client, app):
    seed_filter_data(app)
    today = date.today()
    start = (today - timedelta(days=3)).isoformat()
    html = client.get(f"/transactions?date_from={start}&date_to={today.isoformat()}").get_data(as_text=True)
    assert "Filter coffee" in html
    assert "Airport cab" in html
    assert "Headphones" not in html


def test_sort_oldest_and_newest(client, app):
    seed_filter_data(app)
    old = client.get("/transactions?sort=oldest").get_data(as_text=True)
    assert old.index("Pizza night") < old.index("Headphones") < old.index("Airport cab") < old.index("Filter coffee")

    new = client.get("/transactions?sort=newest").get_data(as_text=True)
    assert new.index("Filter coffee") < new.index("Airport cab") < new.index("Headphones")


def test_invalid_date_filter_is_graceful(client, app):
    seed_filter_data(app)
    html = client.get("/transactions?date_from=not-a-date").get_data(as_text=True)
    assert "Use a valid date" in html

    reversed_range = client.get(
        f"/transactions?date_from={date.today().isoformat()}&date_to=2020-01-01"
    ).get_data(as_text=True)
    assert "start date must be on or before" in reversed_range


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def test_analytics_calculations_and_page(client, app):
    today = date.today()
    insert(app, 500, "Food", "Dining out", today.isoformat())
    insert(app, 500, "Shopping", "Shoes", today.isoformat())
    insert(app, 1000, "Food", "Previous month dining", previous_month_date())

    month_key = today.strftime("%Y-%m")
    response = client.get(f"/analytics?month={month_key}")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Category contributions" in html
    assert "50%" in html
    assert "Monthly comparison" in html
    assert "exactly the same" in html

    with app.app_context():
        data = database.get_analytics_data(today.year, today.month, today=today)
    assert data["total"] == pytest.approx(1000)
    assert data["count"] == 2
    assert data["previous_total"] == pytest.approx(1000)
    assert data["change"] == pytest.approx(0)
    assert len(data["trend"]) == 6
    assert data["trend"][-1]["total"] == pytest.approx(1000)
    assert [row["category"] for row in data["categories"]] == ["Food", "Shopping"]
    assert data["categories"][0]["percent"] == pytest.approx(50)


def test_analytics_without_previous_data(client, app):
    insert(app, 300, "Education", "Course fee", date.today().isoformat())
    html = client.get("/analytics").get_data(as_text=True)
    assert "No baseline" in html
    assert "no percentage baseline yet" in html


def test_invalid_month_falls_back_to_current(client):
    response = client.get("/analytics?month=banana", follow_redirects=True)
    assert response.status_code == 200
    assert "could not be read" in response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_expenses_persist_between_app_instances(client, app):
    client.post(
        "/expenses/add",
        data=payload(description="Persistent lunch"),
        follow_redirects=True,
    )

    second_app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "DATABASE": app.config["DATABASE"],
        }
    )
    with second_app.test_client() as second_client:
        html = second_client.get("/transactions").get_data(as_text=True)
    assert "Persistent lunch" in html


def test_unknown_page_returns_styled_404(client):
    response = client.get("/does-not-exist")
    html = response.get_data(as_text=True)
    assert response.status_code == 404
    assert "Page not found" in html
    assert "Back to dashboard" in html
