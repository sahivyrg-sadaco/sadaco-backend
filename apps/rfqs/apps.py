from django.apps import AppConfig


class RfqsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name  = 'apps.rfqs'
    label = 'rfqs'
    verbose_name = 'Requests for quotation'
