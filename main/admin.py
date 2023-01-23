from django.contrib import admin
from .models import resident, payment, invoice

admin.site.register(resident)
admin.site.register(payment)
admin.site.register(invoice)