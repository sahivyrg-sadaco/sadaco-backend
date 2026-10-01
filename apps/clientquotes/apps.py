from django.apps import AppConfig


class ClientQuotesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name  = 'apps.clientquotes'
    label = 'clientquotes'
    verbose_name = 'Client quotes and purchase orders'
