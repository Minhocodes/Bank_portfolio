import json
import re
import random
from typing import List, Dict, Any, Optional

from django.core.management.base import BaseCommand
from django.db import transaction

from applications.models import Application, Integration, Capability, TechDebtItem
from applications.services.llm_client import ask_llm, LLMError


# ----------------------------
# Allowed values (light validation)
# ----------------------------
ALLOWED_CRITICALITY = {"Low", "Medium", "High"}
ALLOWED_LIFECYCLE = {"Active", "Legacy", "Decommissioning"}
ALLOWED_ENV = {"DEV", "UAT", "PROD"}
ALLOWED_HOSTING = {"on-prem", "cloud", "hybrid"}
ALLOWED_SENSITIVITY = {"Low", "Medium", "High"}
ALLOWED_INTEGRATION_TYPE = {"API", "file", "message"}
ALLOWED_DIRECTION = {"sync", "async"}

OWNERS_BUSINESS = [
    "Head of Payments", "Head of Retail Banking", "Head of Risk", "Head of Compliance",
    "Head of Treasury", "Head of CRM", "Head of Data", "Head of Security"
]
OWNERS_IT = [
    "IT Ops Lead", "Platform Lead", "Integration Lead", "Data Engineering Lead",
    "App Support Lead", "Cloud Lead", "Security Engineering Lead"
]

DB_TECH = ["PostgreSQL", "Oracle", "MS SQL Server", "MySQL", "MongoDB", "DB2", "SQLite"]
VENDOR_PRODUCTS = [
    "SAP PI/PO", "IBM MQ", "Kafka", "MuleSoft", "Apigee", "Temenos T24",
    "Oracle Exadata", "Azure Service Bus", "AWS SQS", "Elastic Stack"
]

CAPABILITIES_POOL = [
    "Customer Onboarding", "KYC/AML Screening", "Payments Processing",
    "Card Management", "Loan Origination", "Fraud Detection", "Reporting & BI",
    "Document Management", "Customer Support", "Authentication/SSO"
]

TECH_DEBT_CATEGORIES = ["Security", "Upgrade", "Performance", "CodeQuality", "Observability", "Reliability"]
TECH_DEBT_STATUS = ["Open", "InProgress", "Done", "WontFix"]
TECH_DEBT_SEVERITY = ["Low", "Medium", "High", "Critical"]

TRANSPORT_POOL = ["REST", "SOAP", "SFTP", "Kafka", "IBM MQ", "gRPC", "Webhooks"]
FREQUENCY_POOL = ["realtime", "hourly", "daily", "weekly", "batch-nightly"]

# ----------------------------
# Small helpers
# ----------------------------
def _norm(v, allowed, fallback):
    if v is None:
        return fallback
    s = str(v).strip()
    return s if s in allowed else fallback


def _clean_str(v, max_len=100, fallback=""):
    if v is None:
        return fallback
    s = str(v).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:max_len] if max_len else s


def _clean_text(v, max_len=2000, fallback=""):
    if v is None:
        return fallback
    s = str(v).strip()
    return s[:max_len]

def _pick(pool, fallback=""):
    return random.choice(pool) if pool else fallback


def _severity_from_debt_score(score: int) -> str:
    if score >= 80:
        return "Critical"
    if score >= 60:
        return "High"
    if score >= 30:
        return "Medium"
    return "Low"

def _strip_code_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _extract_json_object(text: str) -> str:
    """
    Extract first JSON object/array-ish chunk from the text.
    In your previous version you extracted {...}. We'll keep it robust:
    - try {...}
    - if not found, try [...]
    """
    t = _strip_code_fences(text)

    # Prefer {...}
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end != -1 and end > start:
        return t[start:end + 1]

    # Try [...]
    start = t.find("[")
    end = t.rfind("]")
    if start != -1 and end != -1 and end > start:
        return t[start:end + 1]

    raise ValueError("No JSON object/array found in text")


def _repair_json_with_llm(bad_json_text: str) -> str:
    prompt = (
        "Oprav následující text tak, aby to byl VALIDNÍ JSON.\n"
        "Nesmíš nic vysvětlovat. Vrať POUZE JSON.\n\n"
        "TEXT:\n"
        f"{bad_json_text}"
    )
    return ask_llm(prompt).strip()


def _parse_json_robust(raw: str) -> dict:
    """
    Try parse JSON, if fail -> ask LLM to repair.
    """
    json_part = _extract_json_object(raw)
    try:
        data = json.loads(json_part)
        # if list top-level, wrap
        if isinstance(data, list):
            return {"applications": data}
        if isinstance(data, dict):
            return data
        raise ValueError("Unexpected JSON type")
    except Exception:
        fixed = _repair_json_with_llm(json_part)
        fixed_part = _extract_json_object(fixed)
        data = json.loads(fixed_part)
        if isinstance(data, list):
            return {"applications": data}
        return data


def _dedupe_apps_keep_order(apps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplikace podle name (case-insensitive, trim)."""
    seen = set()
    out = []
    for a in apps:
        name = _clean_str(a.get("name"), 200, "").strip()
        key = name.lower()
        if not name:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


# ----------------------------
# Prompts
# ----------------------------
def _prompt_apps(n: int, existing_names: Optional[List[str]] = None) -> str:
    schema = {
        "applications": [
            {
                "name": "string (unique)",
                "domain": "string (Payments|Sales|Risk|CRM|Data|Compliance|Security|CoreBanking)",
                "criticality": "Low|Medium|High",
                "lifecycle": "Active|Legacy|Decommissioning",
                "environment": "DEV|UAT|PROD",
                "region": "string (EU|CZ|DACH|Global)",
                "hosting": "on-prem|cloud|hybrid",
                "tech_stack": "string (comma separated technologies)",
                "runtime": "string (Java|.NET|Python|Node.js|Go)",
                "vendor": "string (Internal|Oracle|Microsoft|SAP|IBM|Temenos)",
                "data_sensitivity": "Low|Medium|High",
                "tech_debt_score": "integer 0-100",
            }
        ]
    }

    avoid = ""
    if existing_names:
        avoid_list = existing_names[:200]
        avoid = (
            "\n\nNEOPAKUJ tato jména (už existují):\n"
            f"{json.dumps(avoid_list, ensure_ascii=False)}"
        )

    return (
        "Vygeneruj mock dataset bankovních aplikací.\n"
        f"Vygeneruj PŘESNĚ {n} aplikací.\n"
        "VÝSTUP MUSÍ BÝT POUZE validní JSON (bez ```).\n"
        "Každá aplikace musí mít unikátní name.\n"
        "Nepiš žádný komentáře ani text mimo JSON."
        f"{avoid}\n\n"
        f"SCHEMA:\n{json.dumps(schema, ensure_ascii=False)}"
    )


def _prompt_integrations(app_names: List[str], n: int) -> str:
    schema = {
        "integrations": [
            {
                "source_app_name": "string (must be in provided list)",
                "target_app_name": "string (must be in provided list and different from source)",
                "integration_type": "API|file|message",
                "direction": "sync|async",
                "daily_volume": "integer",
            }
        ]
    }

    return (
        "Vygeneruj integrace mezi bankovními aplikacemi.\n"
        f"Vygeneruj PŘESNĚ {n} integrací.\n"
        "VÝSTUP MUSÍ BÝT POUZE validní JSON (bez ```).\n"
        "- source_app_name a target_app_name MUSÍ být přesně z tohoto seznamu názvů.\n"
        "- source != target.\n"
        "- Nevracej žádný text mimo JSON.\n\n"
        f"SEZNAM APLIKACÍ:\n{json.dumps(app_names, ensure_ascii=False)}\n\n"
        f"SCHEMA:\n{json.dumps(schema, ensure_ascii=False)}"
    )


# ----------------------------
# Normalization
# ----------------------------
def _normalize_app(a: dict) -> dict:
    debt_score = max(0, min(100, int(a.get("tech_debt_score") or 0)))

    return {
        "name": _clean_str(a.get("name"), 200, "Unnamed App"),
        "domain": _clean_str(a.get("domain"), 100, "General"),
        "criticality": _norm(a.get("criticality"), ALLOWED_CRITICALITY, "Medium"),
        "lifecycle": _norm(a.get("lifecycle"), ALLOWED_LIFECYCLE, "Active"),
        "environment": _norm(a.get("environment"), ALLOWED_ENV, "UAT"),
        "region": _clean_str(a.get("region"), 100, "EU"),
        "hosting": _norm(a.get("hosting"), ALLOWED_HOSTING, "hybrid"),
        "tech_stack": _clean_text(a.get("tech_stack"), 2000, "N/A"),
        "runtime": _clean_str(a.get("runtime"), 100, "N/A"),
        "vendor": _clean_str(a.get("vendor"), 100, "Internal"),
        "data_sensitivity": _norm(a.get("data_sensitivity"), ALLOWED_SENSITIVITY, "Medium"),
        "tech_debt_score": debt_score,
        "business_owner": _clean_str(a.get("business_owner"), 120, _pick(OWNERS_BUSINESS, "Business Owner")),
        "it_owner": _clean_str(a.get("it_owner"), 120, _pick(OWNERS_IT, "IT Owner")),
        "database_technology": _clean_str(a.get("database_technology"), 120, _pick(DB_TECH, "")),
        "vendor_products": _clean_text(
            a.get("vendor_products"),
            500,
            ", ".join(random.sample(VENDOR_PRODUCTS, k=random.randint(1, 3)))
        ),
    }


def _normalize_integration(i: dict) -> dict:
    return {
        "source_app_name": _clean_str(i.get("source_app_name"), 200, ""),
        "target_app_name": _clean_str(i.get("target_app_name"), 200, ""),
        "integration_type": _norm(i.get("integration_type"), ALLOWED_INTEGRATION_TYPE, "API"),
        "direction": _norm(i.get("direction"), ALLOWED_DIRECTION, "async"),
        "daily_volume": int(i.get("daily_volume") or 0),
        "data_sensitivity": _norm(i.get("data_sensitivity"), ALLOWED_SENSITIVITY, "Medium"),
        "transport": _clean_str(i.get("transport"), 80, _pick(TRANSPORT_POOL, "")),
        "frequency": _clean_str(i.get("frequency"), 80, _pick(FREQUENCY_POOL, "")),
        "interface_name": _clean_str(i.get("interface_name"), 120, ""),
    }


def _fallback_integrations(app_names: List[str], n: int) -> List[dict]:
    out = []
    if len(app_names) < 2:
        return out
    for _ in range(n):
        src, tgt = random.sample(app_names, 2)
        out.append({
            "source_app_name": src,
            "target_app_name": tgt,
            "integration_type": random.choice(list(ALLOWED_INTEGRATION_TYPE)),
            "direction": random.choice(list(ALLOWED_DIRECTION)),
            "daily_volume": random.randint(1000, 300000),

            # NEW
            "data_sensitivity": random.choice(list(ALLOWED_SENSITIVITY)),
            "transport": _pick(TRANSPORT_POOL, ""),
            "frequency": _pick(FREQUENCY_POOL, ""),
            "interface_name": f"{src} -> {tgt} interface",
        })
    return out


# ----------------------------
# Command
# ----------------------------
class Command(BaseCommand):
    help = "Seed mock portfolio into SQLite using LLM-generated JSON (robust, batching apps + integrations)"

    def add_arguments(self, parser):
        parser.add_argument("--apps", type=int, default=40, help="Number of applications to generate")
        parser.add_argument("--wipe", action="store_true", help="Delete existing Applications and Integrations before seeding")

        # apps batching
        parser.add_argument("--batch", type=int, default=8, help="How many apps to request per LLM call (default 8)")
        parser.add_argument("--max-attempts", type=int, default=25, help="Max LLM calls for apps generation (default 25)")

        # integrations batching
        parser.add_argument("--int-batch", type=int, default=25, help="How many integrations to request per LLM call (default 25)")
        parser.add_argument("--int-max-attempts", type=int, default=12, help="Max LLM calls for integrations generation (default 12)")

    def handle(self, *args, **options):
        target_apps = int(options["apps"])
        # as before: at least 50, otherwise 2x apps
        target_integrations = max(50, target_apps * 2)
        wipe = options["wipe"]

        batch_size_apps = max(1, int(options["batch"]))
        max_attempts_apps = max(1, int(options["max_attempts"]))

        batch_size_int = max(1, int(options["int_batch"]))
        max_attempts_int = max(1, int(options["int_max_attempts"]))

        # ----------------------------
        # 1) Generate APPS (batched + retries)
        # ----------------------------
        self.stdout.write(self.style.WARNING(
            f"Generating {target_apps} applications via LLM (batch={batch_size_apps})..."
        ))

        collected_apps: List[Dict[str, Any]] = []
        attempt = 0

        while len(collected_apps) < target_apps and attempt < max_attempts_apps:
            attempt += 1
            remaining = target_apps - len(collected_apps)
            n = min(batch_size_apps, remaining)

            existing_names = [_clean_str(a.get("name"), 200, "") for a in collected_apps]
            prompt = _prompt_apps(n, existing_names=existing_names)

            try:
                raw = ask_llm(prompt).strip()
                data = _parse_json_robust(raw)
                batch = data.get("applications", []) or []

                # dedupe within batch + against collected
                batch = _dedupe_apps_keep_order(batch)

                before = len(collected_apps)
                existing_lower = {(_clean_str(a.get("name"), 200, "")).strip().lower() for a in collected_apps}

                for a in batch:
                    nm = _clean_str(a.get("name"), 200, "").strip()
                    if not nm:
                        continue
                    if nm.lower() in existing_lower:
                        continue
                    collected_apps.append(a)
                    existing_lower.add(nm.lower())

                gained = len(collected_apps) - before
                self.stdout.write(self.style.WARNING(
                    f"Apps attempt {attempt}/{max_attempts_apps}: requested {n}, gained {gained}, "
                    f"total {len(collected_apps)}/{target_apps}"
                ))

            except LLMError as e:
                self.stdout.write(self.style.ERROR(f"LLM apps attempt {attempt} failed: {e}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Apps attempt {attempt} parse/other error: {e}"))

        if len(collected_apps) < target_apps:
            self.stdout.write(self.style.WARNING(
                f"LLM produced only {len(collected_apps)}/{target_apps} unique apps after {attempt} attempts. "
                f"Seeding what we have."
            ))

        norm_apps = [_normalize_app(a) for a in collected_apps][:target_apps]

        if not norm_apps:
            self.stdout.write(self.style.ERROR("No applications generated. Nothing to seed."))
            return

        # ----------------------------
        # 2) Seed APPS to DB
        # ----------------------------
        with transaction.atomic():
            if wipe:
                self.stdout.write(self.style.WARNING("Wiping existing data..."))
                TechDebtItem.objects.all().delete()
                Integration.objects.all().delete()
                Application.objects.all().delete()
                Capability.objects.all().delete()

            name_to_app: Dict[str, Application] = {}
            for a in norm_apps:
                obj, _ = Application.objects.get_or_create(name=a["name"])
                obj.domain = a["domain"]
                obj.criticality = a["criticality"]
                obj.lifecycle = a["lifecycle"]
                obj.environment = a["environment"]
                obj.region = a["region"]
                obj.hosting = a["hosting"]
                obj.tech_stack = a["tech_stack"]
                obj.runtime = a["runtime"]
                obj.vendor = a["vendor"]
                obj.data_sensitivity = a["data_sensitivity"]
                obj.tech_debt_score = a["tech_debt_score"]
                obj.save()
                obj.business_owner = a["business_owner"]
                obj.it_owner = a["it_owner"]
                obj.database_technology = a["database_technology"]
                obj.vendor_products = a["vendor_products"]
                obj.save()
                name_to_app[obj.name] = obj

        app_names = list(name_to_app.keys())
        self.stdout.write(self.style.SUCCESS(f"Applications seeded: {len(app_names)}"))
        # ----------------------------
        # 2b) Seed CAPABILITIES + assign to apps
        # ----------------------------
        cap_objects = {}
        for cap_name in CAPABILITIES_POOL:
            cap, _ = Capability.objects.get_or_create(name=cap_name)
            cap_objects[cap_name] = cap

        with transaction.atomic():
            for app in Application.objects.all():
                k = random.randint(2, 5)
                chosen = random.sample(CAPABILITIES_POOL, k=k)
                app.capabilities.set([cap_objects[n] for n in chosen])  
        # ----------------------------
        # 2c) Seed TECH DEBT ITEMS
        # ----------------------------
        created = 0

        with transaction.atomic():
            for app in Application.objects.all():
                items = random.randint(1, 4)
                sev = _severity_from_debt_score(app.tech_debt_score)

                for idx in range(items):
                    cat = _pick(TECH_DEBT_CATEGORIES, "CodeQuality")

                    TechDebtItem.objects.create(
                        application=app,
                        category=cat,
                        severity=sev,
                        status=random.choice(TECH_DEBT_STATUS),
                        title=f"{cat}: issue {idx+1} in {app.name}",
                        description=f"Auto-generated debt item for {app.name}.",
                    )

                    created += 1

        self.stdout.write(self.style.SUCCESS(f"TechDebtItems created: {created}"))
        # ----------------------------
        # 3) Generate INTEGRATIONS (batched + retries + fallback remainder)
        # ----------------------------
        self.stdout.write(self.style.WARNING(
            f"Generating {target_integrations} integrations via LLM (batch={batch_size_int})..."
        ))

        collected_integrations: List[Dict[str, Any]] = []
        attempt = 0

        while len(collected_integrations) < target_integrations and attempt < max_attempts_int:
            attempt += 1
            remaining = target_integrations - len(collected_integrations)
            n = min(batch_size_int, remaining)

            try:
                raw = ask_llm(_prompt_integrations(app_names, n)).strip()
                data = _parse_json_robust(raw)
                batch = data.get("integrations", []) or []

                before = len(collected_integrations)
                collected_integrations.extend(batch)
                gained = len(collected_integrations) - before

                self.stdout.write(self.style.WARNING(
                    f"Integrations attempt {attempt}/{max_attempts_int}: requested {n}, gained {gained}, "
                    f"total {len(collected_integrations)}/{target_integrations}"
                ))
            except LLMError as e:
                self.stdout.write(self.style.ERROR(f"LLM integrations attempt {attempt} failed: {e}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Integrations attempt {attempt} parse/other error: {e}"))

        if len(collected_integrations) < target_integrations:
            missing = target_integrations - len(collected_integrations)
            self.stdout.write(self.style.WARNING(
                f"LLM produced only {len(collected_integrations)}/{target_integrations} integrations. "
                f"Using fallback generator for remaining {missing}."
            ))
            collected_integrations += _fallback_integrations(app_names, missing)

        norm_integrations = [_normalize_integration(i) for i in collected_integrations][:target_integrations]

        # ----------------------------
        # 4) Seed Integrations to DB
        # ----------------------------
        created = 0
        skipped = 0
        with transaction.atomic():
            for it in norm_integrations:
                src = name_to_app.get(it["source_app_name"])
                tgt = name_to_app.get(it["target_app_name"])

                if not src or not tgt or src == tgt:
                    skipped += 1
                    continue

                obj, was_created = Integration.objects.get_or_create(
                    source_app=src,
                    target_app=tgt,
                    integration_type=it["integration_type"],
                    defaults={
                        "direction": it["direction"],
                        "daily_volume": it["daily_volume"],
                    },
                )

                obj.direction = it["direction"]
                obj.daily_volume = it["daily_volume"]
                obj.data_sensitivity = it["data_sensitivity"]
                obj.transport = it["transport"]
                obj.frequency = it["frequency"]
                obj.interface_name = it["interface_name"]
                obj.save()

                if was_created:
                    created += 1

        # ----------------------------
        # 5) HARD COVERAGE: ring over all apps (guarantees 1 outbound + 1 inbound for EVERY app)
        # ----------------------------
        apps = list(Application.objects.all().order_by("id"))
        if len(apps) >= 2:
            ensured = 0
            with transaction.atomic():
                for i, app in enumerate(apps):
                    nxt = apps[(i + 1) % len(apps)]
                    prv = apps[(i - 1) % len(apps)]

                    if not Integration.objects.filter(source_app=app).exists():
                        Integration.objects.create(
                            source_app=app,
                            target_app=nxt,
                            integration_type=random.choice(list(ALLOWED_INTEGRATION_TYPE)),
                            direction=random.choice(list(ALLOWED_DIRECTION)),
                            daily_volume=random.randint(1000, 300000),
                            data_sensitivity=random.choice(list(ALLOWED_SENSITIVITY)),
                            transport=_pick(TRANSPORT_POOL, ""),
                            frequency=_pick(FREQUENCY_POOL, ""),
                            interface_name=f"{app.name} -> {nxt.name} interface",
                        )
                        ensured += 1

                    if not Integration.objects.filter(target_app=app).exists():
                        Integration.objects.create(
                            source_app=prv,
                            target_app=app,
                            integration_type=random.choice(list(ALLOWED_INTEGRATION_TYPE)),
                            direction=random.choice(list(ALLOWED_DIRECTION)),
                            daily_volume=random.randint(1000, 300000),
                            data_sensitivity=random.choice(list(ALLOWED_SENSITIVITY)),
                            transport=_pick(TRANSPORT_POOL, ""),
                            frequency=_pick(FREQUENCY_POOL, ""),
                            interface_name=f"{prv.name} -> {app.name} interface",
                        )
                        ensured += 1

            self.stdout.write(self.style.WARNING(f"Ring coverage ensured. Added {ensured} integrations."))
        else:
            self.stdout.write(self.style.WARNING("Ring coverage skipped (need at least 2 apps)."))





        self.stdout.write(self.style.SUCCESS(f"Integrations created: {created}"))
        self.stdout.write(self.style.WARNING(f"Integrations skipped: {skipped}"))
        self.stdout.write(self.style.SUCCESS("Seed finished ✅"))

