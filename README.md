# SpendWise — Personal Expense Tracker

SpendWise is a local-first personal expense tracker built with **Python, Flask, SQLite and vanilla web technologies**. It gives a clean, dark financial dashboard for recording day-to-day spending, searching transaction history and understanding where money goes each month.

The project is intentionally small and self-contained: no accounts, no cloud services, no payment integrations and no chart libraries. Everything runs on one machine and all records are stored in a local SQLite database.

---

## Features

### Dashboard
- Current-month spending, today's spending, monthly transaction count and average daily spend, all calculated from SQLite records.
- Current-month category breakdown with a CSS donut chart and amounts.
- Six-month spending trend with a CSS/HTML bar chart.
- Recent transactions and a "Month at a glance" panel (largest expense, busiest day, active days).
- Month-over-month comparison on the monthly total.

### Expense management
- Add, view, edit and delete expenses.
- Confirmation dialog before a record is deleted.
- Server-side validation for amount, category, date and an optional description.
- Description is optional; blank descriptions use the category as the transaction title.
- Success/error feedback with dismissible toast notifications.

### Transaction history
- Full transaction list with category, date, amount and actions.
- Search by description (case-insensitive, with SQL `LIKE` wildcards escaped).
- Filter by category and date range.
- Sort by newest or oldest first.
- Distinct empty states for "no records yet" and "no matching results".
- Responsive row layout that becomes a card list on small screens.

### Analytics
- Month picker for any month with recorded data.
- Total, transaction count, daily average and month-over-month change.
- Six-month expenditure chart.
- Category split donut plus a category contribution table with amounts, transaction counts, share bars and percentages.
- Monthly comparison card with previous-month bars and a plain-language verdict.
- Busiest day and top category for the selected month.

### Design
- Deep charcoal surfaces, a restrained mint accent and category-specific colours.
- Sidebar navigation, responsive mobile drawer, rounded cards, consistent spacing and subtle hover/focus transitions.
- No CSS framework, no Bootstrap and no JavaScript chart dependency.
- System font stack so the app works fully offline.

---

## Technology stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.10+, Flask 3.1 |
| Database | SQLite (Python standard library `sqlite3`) |
| Templates | Jinja2 (ships with Flask) |
| Frontend | HTML5, CSS3, vanilla JavaScript |
| Tests | pytest |

No React, Node.js, external chart library or external API is used.

---

## Project structure

```text
SpendWise/
├── app.py                    # Flask app factory, routes, validation, filters
├── database.py               # All SQLite schema and query functions
├── utils.py                  # Currency/date formatting and month helpers
├── seed_demo.py              # Optional demo-data generator
├── requirements.txt
├── pytest.ini
├── README.md
├── .gitignore
├── database/
│   └── .gitkeep              # spendwise.db is created here automatically
├── templates/
│   ├── base.html             # Shared shell, sidebar, toasts, delete dialog
│   ├── _sprite.html          # Inline SVG icon sprite
│   ├── _macros.html          # Reusable icons, category chips and transaction rows
│   ├── dashboard.html
│   ├── transactions.html
│   ├── analytics.html
│   ├── expense_form.html     # Shared add/edit form
│   ├── expense_detail.html
│   └── error.html            # Styled 404 / 500 page
├── static/
│   ├── css/style.css
│   ├── js/app.js
│   └── images/favicon.svg
└── tests/
    ├── conftest.py
    ├── test_app.py
    └── test_utils.py
```

---

## Getting started

### Prerequisites
- Python 3.10 or newer
- `pip`

### 1. Install dependencies

From the project folder:

```bash
python -m venv .venv
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**macOS / Linux:**
```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

### 2. Run the app

```bash
python app.py
```

Open **http://127.0.0.1:5000** in a browser.

The first run automatically creates `database/spendwise.db`, the `expenses` table and its indexes. No manual database setup is required.

The Flask development server is used for this academic project. It is not intended for public deployment.

### 3. Optional demo data

To explore the dashboard with realistic sample transactions:

```bash
python seed_demo.py
```

The script only runs when the database is empty and refuses to modify a database that already contains expenses. Start the app afterwards.

### 4. Reset the database

Stop the server, delete `database/spendwise.db`, then start the app again. A fresh database is created automatically. You may run `python seed_demo.py` again for a clean demo.

### Run the tests

```bash
python -m pytest -q
```

---

## Database

### Schema

```sql
CREATE TABLE expenses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    amount           REAL    NOT NULL CHECK (amount > 0),
    category         TEXT    NOT NULL CHECK (category IN (
        'Food', 'Transportation', 'Shopping', 'Education',
        'Entertainment', 'Healthcare', 'Bills & Utilities', 'Other'
    )),
    description      TEXT    NOT NULL DEFAULT '',
    transaction_date TEXT    NOT NULL CHECK (length(transaction_date) = 10),
    created_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX idx_expenses_date ON expenses (transaction_date);
CREATE INDEX idx_expenses_category ON expenses (category);
```

- Dates are stored as ISO strings (`YYYY-MM-DD`), which keeps range filtering and sorting simple in SQLite.
- Amounts are validated in Python and rounded to two decimal places before storage.
- Descriptions are optional. Whitespace-only input is normalised to an empty string, and the UI uses the category as the title in that case.
- Category names are fixed application configuration, so a separate `categories` table is not necessary for this scope. The icon and colour for each category live in `utils.py`, and the database `CHECK` constraint protects data integrity.
- Every query uses parameter binding (`?`) — no user input is interpolated into SQL.

### Upgrading an existing database
Databases created by versions that required a description are upgraded automatically on the next startup. SQLite cannot remove the old `CHECK` constraint in place, so the table is rebuilt inside a transaction with every row, id and timestamp preserved.

### Indexes
`transaction_date` and `category` are indexed because they are used by dashboard aggregation, date-range filtering, category filtering and sorting.

### Backup
The database is a single file at `database/spendwise.db`. Copy it while the server is stopped to take a backup.

---

## How the numbers are calculated

| Metric | Rule |
| --- | --- |
| This month | Sum of expenses with `transaction_date` from the first day of the current month up to (not including) the first day of the next month. |
| Spent today | Sum of expenses dated today. |
| Transactions this month | Count of current-month expense records. |
| Active days | Number of distinct dates with at least one current-month expense. |
| Daily average | Current-month total ÷ number of elapsed days in the month (e.g. day 15 = 15 days). This avoids measuring future days as zero-spend days. |
| Category percentage | Category total ÷ current/selected month total × 100. |
| Month-over-month change | `(current − previous) ÷ previous × 100`. When the previous month has no spending, the UI reports that no percentage baseline exists instead of dividing by zero. |
| Analytics daily average | For the current month, total ÷ elapsed days. For a completed past month, total ÷ number of days in that month. |
| Busiest day | Date with the highest summed expense amount in the month. |

All figures are recomputed from SQLite on each request; there are no cached or hard-coded totals.

---

## Routes

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/` | Dashboard |
| GET | `/transactions` | Transaction history with `q`, `category`, `date_from`, `date_to` and `sort` query parameters |
| GET | `/analytics` | Analytics with optional `month=YYYY-MM` |
| GET / POST | `/expenses/add` | Create an expense |
| GET | `/expenses/<id>` | View expense details |
| GET / POST | `/expenses/<id>/edit` | Edit an expense |
| POST | `/expenses/<id>/delete` | Delete an expense |

The delete route is POST-only, and the UI asks for confirmation before submitting it.

---

## Validation and error handling

- Amount must be numeric, greater than zero, at most ₹1 crore and have no more than two decimal places.
- Category must be one of the eight predefined categories.
- Description is optional, whitespace-normalised and limited to 160 characters. Blank descriptions are stored as an empty string and displayed using the category name.
- Transaction date must be a real date from 2000 onwards and cannot be in the future.
- Invalid filter dates are ignored with an inline explanation; a start date after the end date is reported to the user.
- Forms preserve submitted values so the user does not have to retype everything after a validation error.
- Database work uses parameterised queries and transactions; unexpected failures render a styled 500 page instead of a stack trace in the browser.
- User text is auto-escaped by Jinja2. A test specifically checks that a `<script>` description is escaped.

---

## Testing performed

Run:

```bash
python -m pytest -q
```

The suite contains **46 automated tests** and covers:

- Database creation, persistence across app instances and migration of older databases without data loss.
- Adding, editing and deleting expenses, including empty, whitespace-only and present descriptions.
- Required amount, category and date fields, plus invalid amounts (zero, negative, too many decimals, non-numeric, above limit), categories, future dates and malformed dates.
- Category-as-title fallback on the dashboard, transaction history and detail pages.
- XSS-safe rendering of descriptions.
- Dashboard totals, today's total, transaction counts, daily average, category percentages and six-month trend values.
- Search (including case-insensitivity and `%` wildcard escaping), category filtering, date-range filtering, newest/oldest sorting and invalid filter handling.
- Analytics totals, percentages, previous-month comparisons, no-baseline states, six-month trend and month fallback for an invalid month.
- 404 pages and styled error responses.
- Indian currency formatting, percentage formatting, month arithmetic, friendly dates and donut gradient generation.

Manual browser verification was also performed at **1440px desktop** and **390px mobile** widths using headless Chrome:

- Add → detail → edit → delete flow with the custom confirmation dialog.
- Empty, whitespace-only and normal descriptions saved successfully; empty ones display the category as the title.
- Empty amount, missing category and missing date were rejected with the correct field errors.
- Category-as-title fallback checked on the dashboard, transaction history and expense detail page.
- An existing database (38 records at migration time) was migrated to the optional-description schema with every row, id and timestamp unchanged.
- Search, filtered empty state and analytics month switching.
- Mobile navigation drawer open/close.
- No horizontal overflow on dashboard, transactions, analytics, add or detail pages.
- No JavaScript console errors.

---

## Design notes

- **No chart dependency:** the donut uses `conic-gradient`, and the monthly charts are styled HTML bars with heights calculated from real totals. This keeps the project easy to explain in a viva.
- **Cohesive shell:** one `base.html` provides the sidebar, mobile top bar, flash toasts and shared delete modal, so all pages feel part of one product.
- **Reusable pieces:** `_macros.html` holds the icon helper, category chip and transaction-row markup used by several pages.
- **Separation of concerns:** routes and validation live in `app.py`, all SQL lives in `database.py`, and formatting/month calculations live in `utils.py`.
- **Responsive behaviour:** the sidebar becomes an overlay drawer under 1120px; stats collapse to two columns and then one; transaction rows become stacked cards under 820px.
- **Accessibility basics:** semantic headings, labels, focus-visible outlines, `aria-current` on the active nav item, an accessible dialog, status toasts and reduced-motion support.

---

## Scope and limitations

This project deliberately does **not** include:

- User accounts, authentication or registration.
- Banking integrations, payment gateways or external financial APIs.
- Cloud sync or mobile applications.
- Budget management, recurring transactions, AI recommendations or multi-currency support.

SpendWise is a single-user, local-first application intended for academic demonstration and personal desktop use.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'flask'`**  
Activate the virtual environment and run `python -m pip install -r requirements.txt`.

**Port 5000 is already in use**  
Stop the other process or run Flask on another port, for example:
```bash
python -c "from app import create_app; create_app().run(port=5001)"
```

**I want a clean start**  
Stop the server, delete `database/spendwise.db`, and run `python app.py` again.

**The dashboard shows zeros**  
That is the correct empty state. Add an expense or run `python seed_demo.py` against an empty database.
