"""Add a non-admin user interactively.

Usage:
    python manage.py add_user
"""
from getpass import getpass
from django.core.management.base import BaseCommand

from apps.accounts.models import User


ROLES = ['admin', 'sales', 'operations', 'finance']


class Command(BaseCommand):
    help = 'Add a user interactively (any role).'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('=== SADACO — Add User ==='))

        email = input('Email: ').strip().lower()
        if not email:
            self.stderr.write('Email is required.')
            return
        if User.objects.filter(email=email).exists():
            self.stderr.write(f'User with email {email} already exists.')
            return

        name = input('Full name: ').strip()

        self.stdout.write('\nSelect role:')
        for i, r in enumerate(ROLES, start=1):
            self.stdout.write(f'  {i}. {r}')
        while True:
            try:
                choice = int(input('Choice [1-4]: ').strip())
                if 1 <= choice <= len(ROLES):
                    role = ROLES[choice - 1]
                    break
            except ValueError:
                pass
            self.stderr.write('Invalid choice.')

        lang = input("Language ([es]/en): ").strip().lower() or 'es'
        if lang not in ('es', 'en'):
            lang = 'es'

        while True:
            pw1 = getpass('Password: ')
            pw2 = getpass('Confirm:  ')
            if pw1 != pw2:
                self.stderr.write('Passwords do not match.')
                continue
            if len(pw1) < 8:
                self.stderr.write('Password must be at least 8 characters.')
                continue
            break

        user = User.objects.create_user(
            email=email, name=name, role=role, password=pw1, lang=lang,
        )
        self.stdout.write(self.style.SUCCESS(
            f'✓ User created: {user.email} ({role})'
        ))
