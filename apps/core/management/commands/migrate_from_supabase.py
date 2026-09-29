"""
Migrate data from an old Supabase Postgres database into the current
Django database.

Usage:
    python manage.py migrate_from_supabase --source-url <SUPABASE_POOLER_URL>

Reads tables in dependency order and uses bulk_create(ignore_conflicts=True)
so re-running the command is safe.
"""
import sys
from django.core.management.base import BaseCommand


TABLE_ORDER = [
    'users',
    'clients',
    'suppliers',
    'deals',
    'deal_items',
    'supplier_quotes',
    'supplier_quote_items',
    'deal_item_splits',
    'payments',
    'invoiced_items',
    'stock_items',
    'stock_movements',
    'delivery_notes',
    'delivery_note_items',
    'file_attachments',       # was 'documents' in Flask — mapped below
    'deal_activities',
    'notifications',
    'assets',
]

# Map legacy Flask table names to their model classes.
# (Legacy table names that don't match the Django model's db_table are
# rewritten before SELECT.)
LEGACY_TABLE_ALIASES = {
    'file_attachments': 'documents',   # Flask stored attachments in `documents`
}


class Command(BaseCommand):
    help = 'Migrate data from an old Supabase DB into this Django DB.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-url', required=True,
            help='Postgres URL of the source Supabase database.',
        )
        parser.add_argument(
            '--batch-size', type=int, default=200,
            help='bulk_create batch size (default 200).',
        )
        parser.add_argument(
            '--tables', type=str, default='',
            help='Comma-separated subset of tables to migrate. '
                 'Default: all tables in dependency order.',
        )

    def handle(self, *args, **opts):
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            self.stderr.write('psycopg2 not installed.')
            sys.exit(1)

        from django.apps import apps as django_apps
        from django.db import transaction

        url = opts['source_url']
        batch_size = opts['batch_size']

        # Build table → model_class map
        table_to_model = {}
        for m in django_apps.get_models():
            t = m._meta.db_table
            table_to_model[t] = m

        tables = [t.strip() for t in (opts['tables'].split(',') if opts['tables'] else TABLE_ORDER) if t.strip()]

        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor,
                                connect_timeout=30, sslmode='require')
        self.stdout.write(self.style.NOTICE(f'Connected to {url.split("@")[-1]}'))

        for table in tables:
            model_table = table
            # Map target Django table to legacy source table if needed
            source_table = LEGACY_TABLE_ALIASES.get(table, table)

            model = table_to_model.get(model_table)
            if not model:
                self.stdout.write(f'  [skip] no model for table `{model_table}`')
                continue

            field_map = {f.column: f for f in model._meta.concrete_fields}

            try:
                with conn.cursor() as cur:
                    cur.execute(f'SELECT * FROM {source_table}')
                    rows = cur.fetchall()
            except Exception as e:
                self.stdout.write(f'  [skip] {source_table}: {e}')
                continue

            if not rows:
                self.stdout.write(f'  {source_table}: 0 rows')
                continue

            objects = []
            for r in rows:
                kwargs = {}
                for col, val in r.items():
                    f = field_map.get(col)
                    if not f:
                        continue
                    kwargs[f.attname] = val
                try:
                    objects.append(model(**kwargs))
                except Exception as e:
                    self.stdout.write(f'    row skipped ({e})')

            try:
                with transaction.atomic():
                    model.objects.bulk_create(
                        objects,
                        batch_size=batch_size,
                        ignore_conflicts=True,
                    )
                self.stdout.write(self.style.SUCCESS(
                    f'  ✓ {model_table}: inserted {len(objects)} rows (from {source_table})'
                ))
            except Exception as e:
                self.stderr.write(f'  ✗ {model_table}: {e}')

        conn.close()
        self.stdout.write(self.style.SUCCESS('\nMigration complete.'))
