from django.contrib import admin
from .models import global_variables, resident, payment, invoice

admin.site.register(global_variables)
admin.site.register(resident)
admin.site.register(payment)
admin.site.register(invoice)
