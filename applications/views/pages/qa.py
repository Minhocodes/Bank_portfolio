import json
import re
import logging
from django.shortcuts import render
from django.http import JsonResponse
from django.core.cache import cache
from django.db.models import Count
from django.views.decorators.http import require_POST
from ...models import Application
from ...services.llm_client import ask_llm, LLMError

logger = logging.getLogger(__name__)

def qa_view(request):
    """
    Jednoduchý Q&A režim:
    - vždy zobrazuje jen poslední otázku a odpověď (uložené v session)
    - do LLM posílá agregované portfolio (ne celý dump)
    """
    last_q = request.session.get("qa_last_question")
    last_a = request.session.get("qa_last_answer")
    error = None

    if request.method == "POST":
        question = (request.POST.get("question") or "").strip()
        if not question:
            error = "Zadej otázku."
        else:
            # rate limit: 1 request / 10s / IP
            cache_key = f"qa:{request.META.get('REMOTE_ADDR')}"
            if cache.get(cache_key):
                error = "Zkus to prosím za chvíli (rate limit)."
            else:
                cache.set(cache_key, True, timeout=10)

                total_apps = Application.objects.count()

                by_domain = list(
                    Application.objects.values("domain")
                    .annotate(cnt=Count("id"))
                    .order_by("-cnt")[:8]
                )

                by_criticality = list(
                    Application.objects.values("criticality")
                    .annotate(cnt=Count("id"))
                    .order_by("-cnt")[:8]
                )

                by_env = list(
                    Application.objects.values("environment")
                    .annotate(cnt=Count("id"))
                    .order_by("-cnt")[:8]
                )

                sample_apps = list(
                    Application.objects.values("id", "name", "domain", "criticality", "environment")[:25]
                )

                portfolio_context = {
                    "total_apps": total_apps,
                    "by_domain_top": by_domain,
                    "by_criticality": by_criticality,
                    "by_environment": by_env,
                    "sample_apps": sample_apps,
                }

                prompt = (
                    "Jsi analytik aplikačního portfolia banky. Odpovídej stručně a konkrétně.\n\n"
                    "POŽADOVANÝ FORMÁT ODPOVĚDI:\n"
                    "1) Stručné shrnutí (1–2 věty)\n"
                    "2) Seznam výsledků jako odrážky. U každé odrážky uveď Application ID a název, "
                    "a krátké odůvodnění vycházející z dat.\n\n"
                    "DATA (agregace + sample):\n"
                    f"{json.dumps(portfolio_context, ensure_ascii=False)}\n\n"
                    "OTÁZKA UŽIVATELE:\n"
                    f"{question}"
                )

                try:
                    answer = ask_llm(prompt)

                    request.session["qa_last_question"] = question
                    request.session["qa_last_answer"] = answer

                    last_q = question
                    last_a = answer

                except LLMError as e:
                    error = f"LLM chyba: {str(e)}"
                except Exception:
                    error = "Nastala neočekávaná chyba."

    # --- NOVĚ: připrav klikací výsledky podle Application ID v odpovědi ---
    linked_apps = []
    if last_a:
        # najde všechna ID ve tvaru "Application ID: 259"
        ids = re.findall(r"Application ID\s*:\s*(\d+)", last_a)

        # odstraní duplicity a zachová pořadí
        ids = list(dict.fromkeys(ids))

        if ids:
            qs = Application.objects.filter(id__in=ids)
            by_id = {str(a.id): a for a in qs}
            linked_apps = [by_id[i] for i in ids if i in by_id]

    return render(request, "applications/qa.html", {
        "last_question": last_q,
        "last_answer": last_a,
        "linked_apps": linked_apps,  # <- přidáno
        "error": error,
    })


@require_POST
def llm_ask(request):
    """
    Očekává JSON:
    {
      "app_id": 123
    }
    Vrací:
    {
      "answer": "..."
    }
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
        app_id = body.get("app_id")

        if not app_id:
            return JsonResponse({"error": "Missing app_id"}, status=400)

        # jednoduchý rate limit: 1 request / 10s / IP (protože nemáš přihlášení)
        cache_key = f"llm:{request.META.get('REMOTE_ADDR')}"
        if cache.get(cache_key):
            return JsonResponse({"error": "Too many requests, try again."}, status=429)
        cache.set(cache_key, True, timeout=10)

        app = Application.objects.get(pk=app_id)

        prompt = (
            f"Napiš krátký profesionální popis bankovní aplikace '{app.name}'. "
            f"Max 5 vět. Zaměř se na účel, funkce a integrace."
        )

        answer = ask_llm(prompt)
        return JsonResponse({"answer": answer})

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    except Application.DoesNotExist:
        return JsonResponse({"error": "Application not found"}, status=404)

    except LLMError:
        logger.exception("LLM call failed")
        return JsonResponse({"error": "LLM temporarily unavailable"}, status=502)

    except Exception:
        logger.exception("Unexpected error in llm_ask")
        return JsonResponse({"error": "Internal server error"}, status=500)