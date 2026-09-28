# SADACO ERP/CRM — Backend

Django 5 + DRF project. Companion to the `frontend/` React app.

## Quick start (local)

```bash
# 1. Install dependencies
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# WeasyPrint system deps
# macOS:  brew install pango
# Ubuntu: apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b

# 2. Configure
cp .env.example .env
# Edit .env — fill in DATABASE_URL and Google Drive credentials

# 3. Migrate + seed + create admin
python manage.py migrate
python manage.py create_admin        # interactive prompt
python manage.py seed_clients        # seeds 9 SADACO clients

# 4. Run
python manage.py runserver           # → http://localhost:8000
```

## Tests

```bash
python manage.py check
python manage.py test
```

## Docker

```bash
docker build -t sadaco-backend .
docker run --env-file .env -p 8080:8080 sadaco-backend
```

## Layout

```
sadaco/                  Django project settings
apps/
  accounts/              Auth, User model (UUID PK + role + lang)
  clients/               Client CRUD + seeded list
  suppliers/             Supplier CRUD + stats endpoint
  deals/                 Deals, DealItems, splits, activity, services
  quotes/                Supplier quotes + line items
  documents/             FileAttachments, delivery notes, generators
                         (doc_generator, pdf_generator, delivery_note_generator)
                         drive_service (Google Drive service-account)
                         db_adapter (shim for the Flask-era generators)
  payments/              Payments + AR services (port of Flask payments.py)
  inventory/             StockItem, StockMovement, adjustment + delivery services
  analytics/             Dashboard query services (port of Flask analytics.py)
  notifications/         Per-user notifications
  core/                  Currency, i18n, permissions, config endpoints,
                         migrate_from_supabase command
```

## Management commands

- `create_admin`             — interactive superuser creation
- `add_user`                 — interactive non-admin user creation (role picker)
- `seed_clients`             — seed the 9 SADACO client records
- `migrate_from_supabase --source-url <url>`
                             — one-shot ETL from a legacy Supabase DB

## API

All endpoints are mounted at `/api/`. Auth is JWT (Bearer). See the spec
document for the complete endpoint map; every URL pattern referenced there
is wired up. Postgres is required for `payments.services` and
`analytics.services` because they use `::DATE`, `::NUMERIC`, `TO_CHAR` and
`FILTER (WHERE ...)` — these are intentional verbatim ports of the Flask SQL.

## Google Drive

`apps/documents/drive_service.py` is the only module that talks to Drive.
Uses a service account — no user OAuth, no Drive sharing for access control.
Provide either `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` (full JSON) or
`GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE` (path) plus
`GOOGLE_DRIVE_ROOT_FOLDER_ID` in the environment.
