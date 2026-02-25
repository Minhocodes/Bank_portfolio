from django.urls import path
from django.views.generic import RedirectView
from .views.pages.dashboard import dashboard_view
from .views.pages.apps import application_list, application_detail
from .services.mermaid import application_mermaid_llm
from .services.llm_client import llm_ask
from .views.pages.qa import qa_view
from .views.pages.analysis import analysis_view
from .views.pages.integrations import (
    integration_list, integration_create, integration_edit, integration_delete
)

urlpatterns = [
    path("", dashboard_view, name="dashboard"),  # homepage = dashboard
    path("apps/", application_list, name="app_list"),
    path("apps/<int:pk>/", application_detail, name="app_detail"),
    path("apps/<int:pk>/mermaid-llm/", application_mermaid_llm, name="app_mermaid_llm"),
    path("analysis/", analysis_view, name="analysis"),
    path("qa/", qa_view, name="qa"),
    path("llm/ask/", llm_ask, name="llm_ask"),
    path("integrations/", integration_list, name="integration_list"),
    path("integrations/create/", integration_create, name="integration_create"),
    path("integrations/<int:pk>/edit/", integration_edit, name="integration_edit"),
    path("integrations/<int:pk>/delete/", integration_delete, name="integration_delete"),
    path("dashboard/", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
]