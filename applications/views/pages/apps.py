from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from ...models import Application



def application_list(request):
    qs = Application.objects.all().order_by("name")

    q = request.GET.get("q", "").strip()
    domain = request.GET.get("domain", "").strip()
    criticality = request.GET.get("criticality", "").strip()
    environment = request.GET.get("environment", "").strip()
    region = request.GET.get("region", "").strip()
    hosting = request.GET.get("hosting", "").strip()
    vendor = request.GET.get("vendor", "").strip()
    sensitivity = request.GET.get("sensitivity", "").strip()

    if q:
        qs = qs.filter(
            Q(name__icontains=q) |
            Q(domain__icontains=q) |
            Q(vendor__icontains=q) |
            Q(tech_stack__icontains=q)
        )

    if domain:
        qs = qs.filter(domain=domain)

    if criticality:
        qs = qs.filter(criticality=criticality)

    if environment:
        qs = qs.filter(environment=environment)

    if region:
        qs = qs.filter(region=region)

    if hosting:
        qs = qs.filter(hosting=hosting)

    if vendor:
        qs = qs.filter(vendor=vendor)

    if sensitivity:
        qs = qs.filter(data_sensitivity=sensitivity)

    # hodnoty pro dropdowny (unikátní + seřazené)
    context = {
        "apps": qs,
        "filters": {
            "q": q,
            "domain": domain,
            "criticality": criticality,
            "environment": environment,
            "region": region,
            "hosting": hosting,
            "vendor": vendor,
            "sensitivity": sensitivity,
        },
        "domains": sorted(Application.objects.values_list("domain", flat=True).distinct()),
        "criticalities": sorted(Application.objects.values_list("criticality", flat=True).distinct()),
        "environments": sorted(Application.objects.values_list("environment", flat=True).distinct()),
        "regions": sorted(Application.objects.values_list("region", flat=True).distinct()),
        "hostings": sorted(Application.objects.values_list("hosting", flat=True).distinct()),
        "vendors": sorted(Application.objects.values_list("vendor", flat=True).distinct()),
        "sensitivities": sorted(Application.objects.values_list("data_sensitivity", flat=True).distinct()),
        "total_count": Application.objects.count(),
        "filtered_count": qs.count(),
    }
    return render(request, "applications/app_list.html", context)


def application_detail(request, pk):
    app = get_object_or_404(Application, pk=pk)

    outbound = app.outbound_integrations.all()
    inbound = app.inbound_integrations.all()

    return render(
        request,
        "applications/app_detail.html",
        {
            "app": app,
            "outbound": outbound,
            "inbound": inbound,
        },
    )