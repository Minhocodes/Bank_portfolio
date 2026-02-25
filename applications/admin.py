from django.contrib import admin
from .models import Application, Integration, Capability, TechDebtItem

admin.site.register(Application)
admin.site.register(Integration)
admin.site.register(Capability)
admin.site.register(TechDebtItem)