from django.urls import path

from . import views

urlpatterns = [
    path("cases/", views.cases),
    path("cases/import/", views.import_case),
    path("cases/<int:pk>/", views.case_detail),
    path("cases/<int:pk>/export/", views.export_case),
    path("cases/<int:pk>/calculate/", views.calculate),
    path("runs/<int:pk>/", views.run_detail),
]
