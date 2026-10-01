from django.contrib import admin

from .models import ClientPO, ClientQuote

admin.site.register(ClientQuote)
admin.site.register(ClientPO)
