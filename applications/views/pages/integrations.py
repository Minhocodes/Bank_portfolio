from django.shortcuts import render, redirect, get_object_or_404
from ...models import Integration, Application



def integration_list(request):
    integrations = (
        Integration.objects.select_related("source_app", "target_app")
        .order_by("-daily_volume")
    )
    apps = Application.objects.all().order_by("name")
    return render(request, "applications/integration_list.html", {
        "integrations": integrations,
        "apps": apps,
    })


def integration_create(request):
    apps = Application.objects.all().order_by("name")

    if request.method == "POST":
        source_id = request.POST.get("source_app")
        target_id = request.POST.get("target_app")

        source_app = get_object_or_404(Application, id=source_id)
        target_app = get_object_or_404(Application, id=target_id)

        Integration.objects.create(
            source_app=source_app,
            target_app=target_app,
            integration_type=request.POST.get("integration_type", "API"),
            direction=request.POST.get("direction", "async"),
            daily_volume=int(request.POST.get("daily_volume") or 0),
            data_sensitivity=request.POST.get("data_sensitivity", "Medium"),
            transport=request.POST.get("transport", ""),
            frequency=request.POST.get("frequency", ""),
            interface_name=request.POST.get("interface_name", ""),
        )
        return redirect("integration_list")

    return render(request, "applications/integration_form.html", {
        "apps": apps,
        "mode": "create",
        "integration": None,
    })


def integration_edit(request, pk: int):
    integration = get_object_or_404(Integration, pk=pk)
    apps = Application.objects.all().order_by("name")

    if request.method == "POST":
        source_id = request.POST.get("source_app")
        target_id = request.POST.get("target_app")

        integration.source_app = get_object_or_404(Application, id=source_id)
        integration.target_app = get_object_or_404(Application, id=target_id)
        integration.integration_type = request.POST.get("integration_type", integration.integration_type)
        integration.direction = request.POST.get("direction", integration.direction)
        integration.daily_volume = int(request.POST.get("daily_volume") or 0)
        integration.data_sensitivity = request.POST.get("data_sensitivity", integration.data_sensitivity)
        integration.transport = request.POST.get("transport", integration.transport)
        integration.frequency = request.POST.get("frequency", integration.frequency)
        integration.interface_name = request.POST.get("interface_name", integration.interface_name)
        integration.save()

        return redirect("integration_list")

    return render(request, "applications/integration_form.html", {
        "apps": apps,
        "mode": "edit",
        "integration": integration,
    })


def integration_delete(request, pk: int):
    integration = get_object_or_404(Integration, pk=pk)

    if request.method == "POST":
        integration.delete()
        return redirect("integration_list")

    return render(request, "applications/integration_delete_confirm.html", {
        "integration": integration
    })