# Automated tests

`apps/core/tests/` checks every business rule: payment terms, costs and margin,
landed cost, freight by weight, payment rules and overrides, the quote → PO →
invoice → supplier-order chain (including partial POs), automatic stages, RFQs,
search, access by owner, roles and login limits.

GitHub runs them on every push (`.github/workflows/tests.yml`) against a real
PostgreSQL, after checking that every database change has its migration file.
See the result on the repository's **Actions** tab, or as a green tick / red
cross next to each commit.

## Deploy only when the tests pass (recommended)

On Render: open the backend service → **Settings** → **Build & Deploy** →
**Auto-Deploy** → choose **After CI Checks Pass** → Save.

From then on a push with a failing test is never deployed; the live app keeps
running the last good version.

## Running them on your computer (optional)

    python manage.py test apps.core.tests

(with DATABASE_URL pointing at a throwaway database, never the live one).
