from django.contrib import admin

from .models import ClientInvoice, Payable, PayablePayment

admin.site.register(ClientInvoice)
admin.site.register(Payable)
admin.site.register(PayablePayment)
