from django.contrib import admin
from network.models import Branch, CalculationRun, Load, Node, Project
admin.site.register([Project, Load, Node, Branch, CalculationRun])
