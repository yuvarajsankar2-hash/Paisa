import os
import re
import secrets
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("EXPENSE_TRACKER_DATABASE", BASE_DIR / "instance" / "expenses.db"))
PASSWORD_MIN_LENGTH = 8
PAGE_SIZE = 10
EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                transaction_date TEXT NOT NULL,
                type TEXT NOT NULL CHECK (type IN ('Debit', 'Credit')),
                reason TEXT NOT NULL,
                amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS transactions_user_date_idx
                ON transactions(user_id, transaction_date DESC, id DESC);
            """
        )


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


def create_app(test_config=None):
    app = Flask(__name__, instance_path=str(BASE_DIR / "instance"))
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("HTTPS_ONLY", "").lower() == "true",
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    init_db()
    app.teardown_appcontext(close_db)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.context_processor(lambda: {"now_year": date.today().year})

    @app.template_filter("display_date")
    def display_date(value):
        return date.fromisoformat(value).strftime("%d-%m-%Y")

    @app.before_request
    def validate_csrf():
        if request.method == "POST":
            submitted = request.form.get("csrf_token", "")
            expected = session.get("csrf_token", "")
            if not expected or not secrets.compare_digest(submitted, expected):
                abort(400, description="Your form session has expired. Please go back, refresh, and try again.")

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("error.html", error=error), 400

    @app.route("/")
    def index():
        if session.get("user_id"):
            return redirect(url_for("home"))
        return redirect(url_for("login"))

    @app.route("/register", methods=("GET", "POST"))
    def register():
        if session.get("user_id"):
            return redirect(url_for("home"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            error = None
            if not all((username, full_name, email, password, confirm_password)):
                error = "Please complete all fields."
            elif not USERNAME_PATTERN.fullmatch(username):
                error = "Username must be 3–30 characters using letters, numbers, dots, underscores, or hyphens."
            elif len(full_name) > 100:
                error = "Full name must be 100 characters or fewer."
            elif not EMAIL_PATTERN.fullmatch(email) or len(email) > 254:
                error = "Enter a valid email address."
            elif len(password) < PASSWORD_MIN_LENGTH:
                error = "Password must be at least 8 characters long."
            elif password != confirm_password:
                error = "Passwords do not match."

            db = get_db()
            if error is None:
                existing = db.execute(
                    "SELECT username, email FROM users WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE",
                    (username, email),
                ).fetchone()
                if existing:
                    error = "That username or email address is already registered."

            if error:
                flash(error, "error")
            else:
                try:
                    db.execute(
                        "INSERT INTO users (username, full_name, email, password_hash, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            username,
                            full_name,
                            email,
                            generate_password_hash(password),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
                    db.commit()
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("That username or email address is already registered.", "error")
                    return render_template("register.html")
                flash("Your account is ready. Please log in.", "success")
                return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if session.get("user_id"):
            return redirect(url_for("home"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute(
                "SELECT id, username, full_name, password_hash FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Incorrect username or password. Please try again.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["full_name"] = user["full_name"]
                csrf_token()
                return redirect(url_for("home"))
        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/password", methods=("GET", "POST"))
    @login_required
    def change_password():
        if request.method == "POST":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            user = get_db().execute(
                "SELECT password_hash FROM users WHERE id = ?", (session["user_id"],)
            ).fetchone()
            error = None
            if not current_password or not new_password or not confirm_password:
                error = "Please complete all fields."
            elif not check_password_hash(user["password_hash"], current_password):
                error = "Your current password is incorrect."
            elif len(new_password) < PASSWORD_MIN_LENGTH:
                error = "New password must be at least 8 characters long."
            elif new_password != confirm_password:
                error = "The new passwords do not match."

            if error:
                flash(error, "error")
            else:
                db = get_db()
                db.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new_password), session["user_id"]),
                )
                db.commit()
                flash("Your password has been updated.", "success")
                return redirect(url_for("home"))
        return render_template("change_password.html")

    @app.route("/home")
    @login_required
    def home():
        db = get_db()
        user_id = session["user_id"]
        today = date.today()
        month_start = today.replace(day=1).isoformat()
        next_month = (
            today.replace(year=today.year + 1, month=1, day=1)
            if today.month == 12
            else today.replace(month=today.month + 1, day=1)
        ).isoformat()
        totals = db.execute(
            """
            SELECT type, COALESCE(SUM(amount_paise), 0) AS total
            FROM transactions
            WHERE user_id = ? AND transaction_date >= ? AND transaction_date < ?
            GROUP BY type
            """,
            (user_id, month_start, next_month),
        ).fetchall()
        summary = {"Debit": 0, "Credit": 0}
        for row in totals:
            summary[row["type"]] = row["total"]
        recent = db.execute(
            """
            SELECT transaction_date, type, reason, amount_paise
            FROM transactions
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 5
            """,
            (user_id,),
        ).fetchall()
        chart_rows = db.execute(
            """
            SELECT substr(transaction_date, 1, 7) AS month, type,
                   SUM(amount_paise) AS total
            FROM transactions
            WHERE user_id = ?
              AND transaction_date >= date('now', 'start of month', '-5 months')
            GROUP BY month, type
            ORDER BY month
            """,
            (user_id,),
        ).fetchall()
        chart_data = {}
        for row in chart_rows:
            chart_data.setdefault(row["month"], {"Debit": 0, "Credit": 0})
            chart_data[row["month"]][row["type"]] = row["total"]
        month_labels = sorted(chart_data)
        chart = {
            "labels": [datetime.strptime(month, "%Y-%m").strftime("%b %Y") for month in month_labels],
            "debits": [chart_data[month]["Debit"] / 100 for month in month_labels],
            "credits": [chart_data[month]["Credit"] / 100 for month in month_labels],
        }
        return render_template(
            "home.html",
            today=today.strftime("%A, %d %B %Y"),
            recent=recent,
            summary=summary,
            chart=chart,
        )

    @app.route("/transactions/add", methods=("GET", "POST"))
    @login_required
    def add_transaction():
        if request.method == "POST":
            transaction_date = request.form.get("transaction_date", "").strip()
            transaction_type = request.form.get("type", "")
            reason = request.form.get("reason", "").strip()
            amount_input = request.form.get("amount", "").strip()
            error = None

            try:
                parsed_date = datetime.strptime(transaction_date, "%d-%m-%Y").date()
                if parsed_date.strftime("%d-%m-%Y") != transaction_date:
                    raise ValueError
                if parsed_date > date.today():
                    error = "Transaction date cannot be in the future."
            except ValueError:
                parsed_date = None
                error = "Enter a valid date in DD-MM-YYYY format."

            if error is None and transaction_type not in ("Debit", "Credit"):
                error = "Choose Debit or Credit as the transaction type."
            elif error is None and (not reason or len(reason) > 200):
                error = "Reason is required and must be 200 characters or fewer."

            amount_paise = None
            if error is None:
                try:
                    amount = Decimal(amount_input)
                    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
                        raise InvalidOperation
                    amount_paise = int(amount * 100)
                    if amount_paise > 9_000_000_000_000_000:
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    error = "Enter a positive amount with no more than two decimal places."

            if error:
                flash(error, "error")
            else:
                db = get_db()
                db.execute(
                    """
                    INSERT INTO transactions
                        (user_id, transaction_date, type, reason, amount_paise, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session["user_id"],
                        parsed_date.isoformat(),
                        transaction_type,
                        reason,
                        amount_paise,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                db.commit()
                flash("Transaction added successfully.", "success")
                return redirect(url_for("transactions"))

        return render_template(
            "add_transaction.html",
            today=date.today().strftime("%d-%m-%Y"),
        )

    @app.route("/transactions")
    @login_required
    def transactions():
        db = get_db()
        user_id = session["user_id"]
        total = db.execute(
            "SELECT COUNT(*) AS count FROM transactions WHERE user_id = ?", (user_id,)
        ).fetchone()["count"]
        page_count = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            page = 1
        page = min(max(page, 1), page_count)
        rows = db.execute(
            """
            SELECT transaction_date, type, reason, amount_paise
            FROM transactions
            WHERE user_id = ?
            ORDER BY transaction_date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, PAGE_SIZE, (page - 1) * PAGE_SIZE),
        ).fetchall()
        return render_template(
            "transactions.html",
            transactions=rows,
            page=page,
            page_count=page_count,
            total=total,
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "").lower() == "true")
