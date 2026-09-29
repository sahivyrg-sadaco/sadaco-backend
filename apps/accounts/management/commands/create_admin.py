"""Create an admin user interactively.

Usage:
    python manage.py create_admin
"""
from getpass import getpass
from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    help = 'Create an admin user interactively.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('=== SADACO — Create Admin User ==='))

        email = input('Email: ').strip().lower()
        if not email:
            self.stderr.write('Email is required.')
            return
        if User.objects.filter(email=email).exists():
            self.stderr.write(f'User with email {email} already exists.')
            return

        name = input('Full name: ').strip()
        if not name:
            self.stderr.write('Name is required.')
            return

        lang = input("Language ([es]/en): ").strip().lower() or 'es'
        if lang not in ('es', 'en'):
            lang = 'es'

        while True:
            pw1 = getpass('Password: ')
            pw2 = getpass('Confirm:  ')
            if pw1 != pw2:
                self.stderr.write('Passwords do not match. Try again.')
                continue
            if len(pw1) < 8:
                self.stderr.write('Password must be at least 8 characters.')
                continue
            break

        user = User.objects.create_superuser(
            email=email, name=name, password=pw1, lang=lang,
        )
        self.stdout.write(self.style.SUCCESS(
            f'✓ Admin created: {user.email} ({user.id})'
        ))
