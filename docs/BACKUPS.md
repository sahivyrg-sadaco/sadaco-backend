# Database backups

A GitHub job (`.github/workflows/backup.yml`) copies the whole database every
night at about 3 am Miami time. Each copy is kept for 30 days as a private
download on GitHub.

## One-time setup

1. In Neon, open the project and copy the connection string
   (Dashboard → Connect). It starts with `postgresql://`.
2. In GitHub, open the **sadaco-backend** repository →
   **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret**.
   - Name: `BACKUP_DATABASE_URL`
   - Secret: paste the connection string
3. Test it: **Actions** tab → **Nightly database backup** → **Run workflow**.
   After a minute or two the run turns green; open it and the backup is
   under **Artifacts** at the bottom.

When the Neon password changes, update this secret too (and `DATABASE_URL` on Render).

## Getting a backup

Actions tab → open a green "Nightly database backup" run → **Artifacts** →
download. It's a zip containing `sadaco-YYYY-MM-DD.dump`.

## Restoring (only if something has gone wrong)

Restore into a **new, empty** database first, check it, and only then point
the app at it. Never restore over the live database in a hurry.

1. In Neon, create a new branch or database and copy its connection string.
2. On a computer with the PostgreSQL 17 tools installed:

       pg_restore --no-owner --no-privileges -d "NEW_CONNECTION_STRING" sadaco-YYYY-MM-DD.dump

3. Check the data (for example, open it with a temporary copy of the app).
4. When happy, set `DATABASE_URL` on Render to the new connection string and redeploy.
