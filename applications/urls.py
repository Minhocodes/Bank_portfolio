from django.urls import path
from .views.dashboard import dashboard_view
from .views.apps import application_list, application_detail
from .views.mermaid import application_mermaid_llm  # application_mermaid jen pokud existuje
from .views.qa import qa_view, llm_ask
from .views.analysis import analysis_view
from .views.integrations import (
    integration_list, integration_create, integration_edit, integration_delete
)

urlpatterns = [
    path("", dashboard_view, name="home"),
    path("apps/", application_list, name="app_list"),
    path("apps/<int:pk>/", application_detail, name="app_detail"),

    # pokud nemáš application_mermaid, nedávej ho sem
    # path("apps/<int:pk>/mermaid/", application_mermaid, name="app_mermaid"),
    path("apps/<int:pk>/mermaid-llm/", application_mermaid_llm, name="app_mermaid_llm"),

    path("llm/ask/", llm_ask, name="llm_ask"),
    path("qa/", qa_view, name="qa"),
    path("analysis/", analysis_view, name="analysis"),

    path("integrations/", integration_list, name="integration_list"),
    path("integrations/create/", integration_create, name="integration_create"),
    path("integrations/<int:pk>/edit/", integration_edit, name="integration_edit"),
    path("integrations/<int:pk>/delete/", integration_delete, name="integration_delete"),

    path("dashboard/", dashboard_view, name="dashboard"),
]