import json
import logging
from django.shortcuts import render, get_object_or_404
from django.core.cache import cache
from ..models import Application
from ..services.llm_client import ask_llm, LLMError

logger = logging.getLogger(__name__)
def application_mermaid(request, pk):
    """
    Původní (ne-LLM) Mermaid generování – nechávám pro fallback/debug.
    """
    app = get_object_or_404(Application, pk=pk)

    outbound = app.outbound_integrations.select_related("target_app").all()
    inbound = app.inbound_integrations.select_related("source_app").all()

    lines = [
        "flowchart LR",
        "  classDef app fill:#f3f0ff,stroke:#7c3aed,stroke-width:2px;",
    ]

    def node_id(a):
        return f"app_{a.id}"

    # hlavní uzel
    lines.append(f'  {node_id(app)}["{app.name}"]')
    lines.append(f"  class {node_id(app)} app")

    # inbound
    for i in inbound:
        src = i.source_app
        lines.append(f'  {node_id(src)}["{src.name}"]')
        lines.append(f"  class {node_id(src)} app")
        lines.append(f'  {node_id(src)} -->|"{i.integration_type}"| {node_id(app)}')

    # outbound
    for i in outbound:
        tgt = i.target_app
        lines.append(f'  {node_id(tgt)}["{tgt.name}"]')
        lines.append(f"  class {node_id(tgt)} app")
        lines.append(f'  {node_id(app)} -->|"{i.integration_type}"| {node_id(tgt)}')

    mermaid = "\n".join(lines)
    return render(request, "applications/mermaid.html", {"app": app, "mermaid": mermaid})


# -------- Mermaid přes LLM: generate -> check -> 1x fix --------

def _build_mermaid_prompt(app, inbound, outbound):
    ctx = {
        "app": {"id": app.id, "name": app.name},
        "inbound": [
            {
                "source_app": {"id": i.source_app.id, "name": i.source_app.name},
                "integration_type": i.integration_type,
            }
            for i in inbound
        ],
        "outbound": [
            {
                "target_app": {"id": i.target_app.id, "name": i.target_app.name},
                "integration_type": i.integration_type,
            }
            for i in outbound
        ],
        "rules": {
            "direction": "flowchart LR",
            "node_id_format": "app_<id>",
            "edges": {
                "inbound": "source -->|integration_type| main",
                "outbound": "main -->|integration_type| target",
            },
        },
    }

    return (
        "Vygeneruj Mermaid diagram pro integrační okolí bankovní aplikace.\n"
        "VÝSTUP MUSÍ BÝT POUZE Mermaid kód (bez Markdown fence ```).\n\n"
        "POŽADAVKY:\n"
        "- Začni přesně řádkem: flowchart LR\n"
        "- Node id používej: app_<id>\n"
        "- Popisky uzlů dej jako [\"Název aplikace\"]\n"
        "- Inbound hrany: app_source -->|\"integration_type\"| app_main\n"
        "- Outbound hrany: app_main -->|\"integration_type\"| app_target\n\n"
        "DATA:\n"
        f"{json.dumps(ctx, ensure_ascii=False)}"
    )


def _build_mermaid_check_prompt(mermaid_code):
    return (
        "Zkontroluj následující Mermaid kód.\n"
        "Pokud je validní a dává smysl jako flowchart, vrať přesně: OK\n"
        "Pokud není validní, vrať opravený Mermaid kód (pouze kód, bez ```).\n\n"
        "KÓD:\n"
        f"{mermaid_code}"
    )


def application_mermaid_llm(request, pk):
    app = get_object_or_404(Application, pk=pk)

    outbound = app.outbound_integrations.select_related("target_app").all()
    inbound = app.inbound_integrations.select_related("source_app").all()

    try:
        # rate limit: 1 request / 10s / IP
        cache_key = f"mermaid_llm:{request.META.get('REMOTE_ADDR')}"
        if cache.get(cache_key):
            return render(request, "applications/mermaid.html", {
                "app": app,
                "mermaid": "",
                "error": "Zkus to prosím za chvíli (rate limit).",
            })
        cache.set(cache_key, True, timeout=10)

        # 1) generace
        prompt = _build_mermaid_prompt(app, inbound, outbound)
        mermaid = ask_llm(prompt).strip()

        # 2) check (a případně 1x oprava)
        check_prompt = _build_mermaid_check_prompt(mermaid)
        check_result = ask_llm(check_prompt).strip()

        if check_result != "OK":
            # check_result je opravený mermaid kód (1 pokus o opravu)
            mermaid = check_result.strip()

            # ještě jednou ověřit (už bez další opravy)
            verify = ask_llm(_build_mermaid_check_prompt(mermaid)).strip()
            if verify != "OK":
                return render(request, "applications/mermaid.html", {
                    "app": app,
                    "mermaid": mermaid,
                    "error": "Mermaid se nepodařilo ověřit ani po jedné opravě. Zkus kliknout znovu.",
                })

        return render(request, "applications/mermaid.html", {"app": app, "mermaid": mermaid})

    except LLMError as e:
        return render(request, "applications/mermaid.html", {
            "app": app,
            "mermaid": "",
            "error": f"LLM chyba: {str(e)}",
        })
    except Exception:
        logger.exception("Unexpected error in application_mermaid_llm")
        return render(request, "applications/mermaid.html", {
            "app": app,
            "mermaid": "",
            "error": "Nastala neočekávaná chyba.",
        })