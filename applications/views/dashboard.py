from django.shortcuts import render
from django.db.models import Count, Avg
from ..models import Application

def dashboard_view(request):
    total_apps = Application.objects.count()

    criticality_counts_qs = (
        Application.objects.values("criticality")
        .annotate(c=Count("id"))
        .order_by("-c")
    )
    env_counts_qs = (
        Application.objects.values("environment")
        .annotate(c=Count("id"))
        .order_by("-c")
    )

    # jednoduché "top 5" – nejvyšší tech debt score
    top_debt = Application.objects.order_by("-tech_debt_score")[:5]

    # průměrný tech debt (jen pro rychlou metriku)
    avg_debt = Application.objects.aggregate(avg=Avg("tech_debt_score"))["avg"] or 0

    # převeď na dicty pro Chart.js
    criticality_labels = [x["criticality"] or "N/A" for x in criticality_counts_qs]
    criticality_values = [x["c"] for x in criticality_counts_qs]

    env_labels = [x["environment"] or "N/A" for x in env_counts_qs]
    env_values = [x["c"] for x in env_counts_qs]

    context = {
        "total_apps": total_apps,
        "avg_debt": round(avg_debt, 1),
        "top_debt": top_debt,
        "criticality_labels": criticality_labels,
        "criticality_values": criticality_values,
        "env_labels": env_labels,
        "env_values": env_values,
    }
    return render(request, "applications/dashboard.html", context)