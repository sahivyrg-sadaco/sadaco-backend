"""Seed the SADACO client list.

Usage:
    python manage.py seed_clients
"""
from django.core.management.base import BaseCommand

from apps.clients.models import Client


CLIENTS = [
    {
        'dropdown_name':  'ALCASA',
        'full_name':      'C.V.G. Aluminio del Caroní S.A.',
        'code':           74,
        'country':        'Venezuela',
    },
    {
        'dropdown_name':  'CASIMA',
        'full_name':      'CASIMA',
        'code':           32,
    },
    {
        'dropdown_name':  'CLOVER',
        'full_name':      'CLOVER',
        'code':           25,
    },
    {
        'dropdown_name':  'MASISA',
        'full_name':      'MASISA S.A.',
        'code':           23,
    },
    {
        'dropdown_name':  'REFRACTARIA SOCIALISTA',
        'full_name':      'CVG Refractarios C.A.',
        'code':           13,
        'country':        'Venezuela',
    },
    {
        'dropdown_name':  'SIDOR',
        'full_name':      'Siderúrgica de Orinoco C.A.',
        'code':           17,
        'country':        'Venezuela',
    },
    {
        'dropdown_name':  'VENALUM',
        'full_name':      'CVG Venalum C.A.',
        'code':           54,
        'country':        'Venezuela',
    },
    {
        'dropdown_name':  'SADACO CA',
        'full_name':      'SADACO C.A.',
        'code':           7,
        'country':        'Venezuela',
        'address_line1':  'Av. Las Americas. Torre Loreto II. Piso 1. Ofic: 102.',
        'address_line2':  'Puerto Ordaz, Bolívar, Venezuela',
    },
    {
        'dropdown_name':  'SIDERALLOYS',
        'full_name':      'SiderAlloys International S.A.',
        'code':           96,
        'country':        'Switzerland',
        'address_line1':  'Via Cantonale 1',
        'address_line2':  '6900 Lugano, Switzerland',
        'contact_name':   'Edoardo Dodero',
    },
]


class Command(BaseCommand):
    help = 'Seed the standard 9 SADACO clients.'

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for data in CLIENTS:
            obj, was_created = Client.objects.update_or_create(
                code=data['code'],
                defaults=data,
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'+ {obj.dropdown_name}'))
            else:
                updated += 1
                self.stdout.write(f'~ {obj.dropdown_name} (updated)')

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Done. {created} created, {updated} updated.'
        ))
