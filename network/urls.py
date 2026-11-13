from django.urls import path
from network import views

urlpatterns = [
    path("", views.ProjectListView.as_view(), name="project_list"),
    path("projects/new/", views.ProjectCreateView.as_view(), name="project_create"),
    path("projects/import/", views.project_import, name="project_import"),
    path("projects/<int:pk>/", views.ProjectDetailView.as_view(), name="project_detail"),
    path("projects/<int:pk>/edit/", views.ProjectUpdateView.as_view(), name="project_edit"),
    path("projects/<int:pk>/delete/", views.ProjectDeleteView.as_view(), name="project_delete"),
    path("projects/<int:pk>/run/", views.project_run, name="project_run"),
    path("projects/<int:pk>/export/", views.project_export, name="project_export"),
    path("projects/<int:pk>/runs/<int:run_pk>/", views.run_detail, name="run_detail"),
    path("projects/<int:pk>/runs/<int:run_pk>/status/", views.run_status, name="run_status"),
    path("projects/<int:pk>/<str:kind>/add/", views.item_create, name="item_create"),
    path("projects/<int:pk>/<str:kind>/<int:item_pk>/edit/", views.item_edit, name="item_edit"),
    path("projects/<int:pk>/<str:kind>/<int:item_pk>/delete/", views.item_delete, name="item_delete"),
]
