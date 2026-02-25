import time
import requests
from django.conf import settings


class LLMError(Exception):
    pass


def _get_timeout() -> int:
    # když není nastaveno, dej rozumný default
    return int(getattr(settings, "LLM_TIMEOUT_SECONDS", 60) or 60)


def _get_model() -> str:
    model = getattr(settings, "LLM_MODEL", None)
    if not model:
        # fallback kdyby ses zapomněl nastavit
        return "gpt-4o-mini"
    return model


def ask_llm(prompt: str) -> str:
    if not getattr(settings, "LLM_API_KEY", None):
        raise LLMError("Missing LLM_API_KEY")

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": _get_model(),
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        # důležité: omezí délku odpovědi => rychlejší, menší šance na timeout
        "max_tokens": int(getattr(settings, "LLM_MAX_TOKENS", 600) or 600),
    }

    timeout_seconds = _get_timeout()

    # 1 retry na timeout (typicky stačí)
    for attempt in range(2):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)

            if r.status_code >= 400:
                # zkus vyčíst detail z JSON erroru
                try:
                    err = r.json().get("error", {})
                    msg = err.get("message") or r.text
                except Exception:
                    msg = r.text
                raise LLMError(f"LLM HTTP {r.status_code}: {msg}")

            data = r.json()
            return data["choices"][0]["message"]["content"]

        except requests.Timeout:
            if attempt == 0:
                # krátká pauza a retry
                time.sleep(0.4)
                continue
            raise LLMError(f"LLM request timed out (timeout={timeout_seconds}s)")

        except requests.RequestException as e:
            raise LLMError(f"LLM request failed: {e}")

    raise LLMError("LLM request failed")