import json
import logging
from django.shortcuts import render
from django.core.cache import cache
from django.db.models import Count
from ...models import Application
from ...services.llm_client import ask_llm, LLMError

logger = logging.getLogger(__name__)
def analysis_view(request):
    """
    Globální LLM analýza portfolia:
    - shrnutí
    - hlavní rizika
    - top 5 kandidátů na modernizaci

    Optimalizace proti timeoutům:
    - posílá menší subset dat
    - cachuje výsledek
    """

    result = None
    error = None

    # cache celé analýzy na 5 minut (ať se to zbytečně negeneruje)
    cached = cache.get("analysis:latest")
    if cached:
        return render(request, "applications/analysis.html", {"result": cached, "error": None})

    try:
        # rate limit 1 request / 10s / IP
        ip = request.META.get("REMOTE_ADDR")
        cache_key = f"analysis:rl:{ip}"
        if cache.get(cache_key):
            return render(request, "applications/analysis.html", {
                "result": None,
                "error": "Zkus to prosím za chvíli (rate limit).",
            })
        cache.set(cache_key, True, timeout=10)

        total_apps = Application.objects.count()

        # zúžené agregace (top 6)
        by_domain = list(
            Application.objects.values("domain")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")[:6]
        )

        by_criticality = list(
            Application.objects.values("criticality")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")[:6]
        )

        by_env = list(
            Application.objects.values("environment")
            .annotate(cnt=Count("id"))
            .order_by("-cnt")[:6]
        )

        # malý sample (15) jen s klíčovými poli
        sample_apps = list(
            Application.objects.values("id", "name", "domain", "criticality", "environment")[:15]
        )

        portfolio_context = {
            "total_apps": total_apps,
            "top_by_domain": by_domain,
            "top_by_criticality": by_criticality,
            "top_by_environment": by_env,
            "sample_apps": sample_apps,
        }

        prompt = (
            "Jsi senior enterprise architekt banky. "
            "Na základě dat proveď rychlou analýzu aplikačního portfolia.\n\n"
            "Piš česky a stručně. Max 250–350 slov.\n\n"
            "FORMÁT:\n"
            "1) Shrnutí (2–3 věty)\n"
            "2) 3 hlavní rizika (odrážky)\n"
            "3) Top 5 aplikací k modernizaci (ID + název + 1 věta proč)\n"
            "4) 3 doporučené další kroky\n\n"
            "DATA:\n"
            f"{json.dumps(portfolio_context, ensure_ascii=False)}"
        )

        result = ask_llm(prompt)

        # ulož do cache na 5 minut
        cache.set("analysis:latest", result, timeout=300)

    except LLMError as e:
        error = f"LLM chyba: {str(e)}"
    except Exception:
        logger.exception("Unexpected error in analysis_view")
        error = "Nastala neočekávaná chyba."

    return render(request, "applications/analysis.html", {"result": result, "error": error})