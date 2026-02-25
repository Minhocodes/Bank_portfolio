from django.urls import path
from django.views.generic import RedirectView
from .views.dashboard import dashboard_view
from .views.apps import application_list, application_detail
from .views.mermaid import application_mermaid_llm
from .views.qa import qa_view, llm_ask
from .views.analysis import analysis_view
from .views.integrations import (
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