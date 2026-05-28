from django.contrib import admin
from .models import global_variables, resident, payment, invoice, sefton_payment, sefton_login_details, sefton_action_item

admin.site.register(global_variables)
admin.site.register(resident)
admin.site.register(payment)
admin.site.register(invoice)
admin.site.register(sefton_payment)
admin.site.register(sefton_login_details)
admin.site.register(sefton_action_item)
