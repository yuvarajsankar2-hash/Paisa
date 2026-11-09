# Paisa — Personal Expense Tracker

A responsive Flask and SQLite expense tracker with account registration, private transaction history, monthly summaries, and an income/expense chart.

## Features

- Register and log in with unique usernames and email addresses.
- Passwords are stored as secure Werkzeug password hashes; sessions use HTTP-only, same-site cookies.
- Session-authenticated pages and CSRF validation for every form submission.
- Add Debit and Credit transactions with validated dates, reasons, and rupee amounts.
- View private transaction history in pages of 10.
- Review the five latest entries, this month's totals, and recent monthly trends.
- Change password and log out from the account menu.

## Run locally

1. Use Python 3.10 or later.
2. (Optional) Create and activate a virtual environment.
3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Set a persistent secret key for sessions:

   ```powershell
   $env:SECRET_KEY = "replace-this-with-a-long-random-secret"
   ```

5. Start the server:

   ```powershell
   python app.py
   ```

6. Open <http://127.0.0.1:5000>.

The SQLite database is created at `instance/expenses.db`. Set `EXPENSE_TRACKER_DATABASE` to use another database file. For deployment behind HTTPS, set `HTTPS_ONLY=true` and run with a production WSGI server; do not enable Flask debug mode in production.

Bootstrap, Chart.js, and the optional font are loaded from CDNs.
