from .pages.dashboard import dashboard_view
from .pages.apps import application_list, application_detail
from ..services.mermaid import application_mermaid, application_mermaid_llm
from .pages.qa import qa_view, llm_ask
from .pages.analysis import analysis_view
from .pages.integrations import integration_list, integration_create, integration_edit, integration_delete