"""SpendWise — a local-first personal expense tracker built with Flask."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from flask import (
    Blueprint,
    Flask,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

import database
from utils import (
    CATEGORIES,
    CATEGORY_NAMES,
    MAX_AMOUNT,
    donut_gradient,
    expense_title,
    format_datetime,
    format_inr,
    format_percent,
    friendly_date,
    full_date,
    month_label,
    parse_month,
    short_date,
)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DATABASE = BASE_DIR / "database" / "spendwise.db"

main = Blueprint("main", __name__)


def create_app(test_config: dict | None = None) -> Flask:
    """Application factory used by both `python app.py` and the tests."""
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SPENDWISE_SECRET_KEY", "spendwise-local-dev-key"),
        DATABASE=os.environ.get("SPENDWISE_DATABASE", str(DEFAULT_DATABASE)),
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    database.init_app(app)
    with app.app_context():
        database.init_db()

    app.register_blueprint(main)
    _register_template_helpers(app)
    return app


def _register_template_helpers(app: Flask) -> None:
    app.jinja_env.filters.update(
        {
            "inr": format_inr,
            "inr_compact": lambda value: format_inr(value, compact=True),
            "pct": format_percent,
            "friendly_date": friendly_date,
            "short_date": short_date,
            "full_date": full_date,
            "datetime_display": format_datetime,
            "month_label": month_label,
        }
    )
    app.jinja_env.globals.update(
        CATEGORIES=CATEGORIES,
        CATEGORY_NAMES=CATEGORY_NAMES,
        donut_gradient=donut_gradient,
        expense_title=expense_title,
    )


@main.app_context_processor
def inject_globals() -> dict:
    today = date.today()
    return {
        "today": today,
        "today_iso": today.isoformat(),
        "current_month_iso": today.strftime("%Y-%m"),
        "current_month_label": f"{today.strftime('%B')} {today.year}",
    }


@main.get("/")
def dashboard():
    data = database.get_dashboard_data()
    return render_template(
        "dashboard.html",
        active_page="dashboard",
        data=data,
    )


@main.get("/transactions")
def transactions():
    filters = {
        "q": request.args.get("q", "").strip(),
        "category": request.args.get("category", "").strip(),
        "date_from": request.args.get("date_from", "").strip(),
        "date_to": request.args.get("date_to", "").strip(),
        "sort": request.args.get("sort", "newest").strip(),
    }
    errors: dict[str, str] = {}

    if filters["category"] and filters["category"] not in CATEGORIES:
        filters["category"] = ""
    if filters["sort"] not in {"newest", "oldest"}:
        filters["sort"] = "newest"

    for field in ("date_from", "date_to"):
        if filters[field]:
            try:
                date.fromisoformat(filters[field])
            except ValueError:
                errors[field] = "Use a valid date."
                filters[field] = ""

    if filters["date_from"] and filters["date_to"] and filters["date_from"] > filters["date_to"]:
        errors["date_range"] = "The start date must be on or before the end date."

    expenses = database.get_expenses(filters)
    filtered_total = sum(item["amount"] for item in expenses)
    filters_active = any(
        filters[key] for key in ("q", "category", "date_from", "date_to")
    ) or filters["sort"] != "newest"
    total_expenses = database.count_expenses()

    return render_template(
        "transactions.html",
        active_page="transactions",
        expenses=expenses,
        filters=filters,
        errors=errors,
        filtered_total=filtered_total,
        filters_active=filters_active,
        total_expenses=total_expenses,
    )


@main.get("/analytics")
def analytics():
    requested = request.args.get("month", "")
    parsed = parse_month(requested)
    if parsed:
        year, month = parsed
    else:
        today = date.today()
        year, month = today.year, today.month
        if requested:
            flash("That month could not be read, so the current month is shown.", "info")

    data = database.get_analytics_data(year, month)
    today = date.today()
    selected_is_current = (year, month) == (today.year, today.month)
    return render_template(
        "analytics.html",
        active_page="analytics",
        data=data,
        selected_is_current=selected_is_current,
    )


def _empty_form_values() -> dict:
    return {
        "amount": "",
        "category": "",
        "description": "",
        "transaction_date": date.today().isoformat(),
    }


def _validate_expense_form(form) -> tuple[dict, dict, dict]:
    """Return cleaned data, field errors and submitted values."""
    values = {
        "amount": form.get("amount", "").strip(),
        "category": form.get("category", "").strip(),
        "description": form.get("description", "").strip(),
        "transaction_date": form.get("transaction_date", "").strip(),
    }
    errors: dict[str, str] = {}
    cleaned: dict = {}

    amount_raw = values["amount"]
    if not amount_raw:
        errors["amount"] = "Enter an amount."
    else:
        try:
            amount = Decimal(amount_raw)
            if not amount.is_finite():
                raise InvalidOperation
            if amount <= 0:
                errors["amount"] = "Amount must be greater than zero."
            elif amount > MAX_AMOUNT:
                errors["amount"] = "Amount must be ₹1 crore or less."
            elif -amount.as_tuple().exponent > 2:
                errors["amount"] = "Use at most two decimal places."
            else:
                cleaned["amount"] = float(amount.quantize(Decimal("0.01")))
        except (InvalidOperation, ValueError):
            errors["amount"] = "Enter a valid amount."

    if not values["category"]:
        errors["category"] = "Choose a category."
    elif values["category"] not in CATEGORIES:
        errors["category"] = "Choose a valid category."
    else:
        cleaned["category"] = values["category"]

    description = " ".join(values["description"].split())
    values["description"] = description
    if len(description) > 160:
        errors["description"] = "Keep the description under 160 characters."
    else:
        cleaned["description"] = description

    if not values["transaction_date"]:
        errors["transaction_date"] = "Choose a transaction date."
    else:
        try:
            txn_date = date.fromisoformat(values["transaction_date"])
            if txn_date > date.today():
                errors["transaction_date"] = "The date cannot be in the future."
            elif txn_date < date(2000, 1, 1):
                errors["transaction_date"] = "Choose a date from 2000 onwards."
            else:
                cleaned["transaction_date"] = txn_date.isoformat()
        except ValueError:
            errors["transaction_date"] = "Enter a valid date."

    return cleaned, errors, values


@main.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if request.method == "POST":
        cleaned, errors, values = _validate_expense_form(request.form)
        if not errors:
            expense_id = database.create_expense(**cleaned)
            flash("Expense added successfully.", "success")
            return redirect(url_for("main.expense_detail", expense_id=expense_id))
        flash("Please fix the highlighted fields.", "error")
    else:
        values = _empty_form_values()
        errors = {}

    return render_template(
        "expense_form.html",
        active_page="transactions",
        mode="add",
        errors=errors,
        values=values,
        expense=None,
    )


@main.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
def edit_expense(expense_id: int):
    expense = database.get_expense(expense_id)
    if expense is None:
        return _not_found("That expense does not exist.")

    if request.method == "POST":
        cleaned, errors, values = _validate_expense_form(request.form)
        if not errors:
            database.update_expense(expense_id, **cleaned)
            flash("Expense updated successfully.", "success")
            return redirect(url_for("main.expense_detail", expense_id=expense_id))
        flash("Please fix the highlighted fields.", "error")
    else:
        values = {
            "amount": f"{expense['amount']:.2f}".rstrip("0").rstrip("."),
            "category": expense["category"],
            "description": expense["description"],
            "transaction_date": expense["transaction_date"],
        }
        errors = {}

    return render_template(
        "expense_form.html",
        active_page="transactions",
        mode="edit",
        errors=errors,
        values=values,
        expense=expense,
    )


@main.post("/expenses/<int:expense_id>/delete")
def delete_expense(expense_id: int):
    expense = database.get_expense(expense_id)
    if expense is None:
        return _not_found("That expense does not exist.")
    database.delete_expense(expense_id)
    flash("Expense deleted.", "success")
    return redirect(url_for("main.transactions"))


@main.get("/expenses/<int:expense_id>")
def expense_detail(expense_id: int):
    expense = database.get_expense(expense_id)
    if expense is None:
        return _not_found("That expense does not exist.")
    return render_template(
        "expense_detail.html",
        active_page="transactions",
        expense=expense,
    )


def _not_found(message: str):
    return (
        render_template(
            "error.html",
            active_page="",
            code=404,
            title="Page not found",
            message=message,
        ),
        404,
    )


@main.app_errorhandler(404)
def not_found(_error):
    return _not_found("The page you are looking for could not be found.")


@main.app_errorhandler(500)
def server_error(_error):
    return (
        render_template(
            "error.html",
            active_page="",
            code=500,
            title="Something went wrong",
            message="SpendWise could not complete that request. Please try again.",
        ),
        500,
    )


if __name__ == "__main__":
    create_app().run(debug=True)
