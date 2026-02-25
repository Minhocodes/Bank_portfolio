from django.db import models


class Capability(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Application(models.Model):
    name = models.CharField(max_length=200)
    domain = models.CharField(max_length=100)
    criticality = models.CharField(max_length=50)
    lifecycle = models.CharField(max_length=50)

    environment = models.CharField(max_length=50)
    region = models.CharField(max_length=100)
    hosting = models.CharField(max_length=50)

    # Ownership (DB scope)
    business_owner = models.CharField(max_length=120, blank=True)
    it_owner = models.CharField(max_length=120, blank=True)
    vendor = models.CharField(max_length=100)  # necháme string (rychlé, neriskuje migrace)

    # Technology (DB scope)
    tech_stack = models.TextField()
    runtime = models.CharField(max_length=100)
    database_technology = models.CharField(max_length=120, blank=True)  # NEW: DB tech
    vendor_products = models.TextField(blank=True)  # NEW: "Oracle Exadata, SAP PI, ..."

    # Data / risk
    data_sensitivity = models.CharField(max_length=50)
    tech_debt_score = models.IntegerField(default=0)

    # Capability (DB scope)
    capabilities = models.ManyToManyField(Capability, blank=True, related_name="applications")

    def __str__(self):
        return self.name


class Integration(models.Model):
    source_app = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="outbound_integrations"
    )
    target_app = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="inbound_integrations"
    )

    # Integration basics
    integration_type = models.CharField(max_length=50)  # API / file / message
    direction = models.CharField(max_length=50)  # sync / async (charakter)
    daily_volume = models.IntegerField(default=0)

    # NEW: scope fields
    data_sensitivity = models.CharField(max_length=50, blank=True)  # Low/Medium/High
    transport = models.CharField(max_length=80, blank=True)  # REST, SOAP, SFTP, Kafka, MQ...
    frequency = models.CharField(max_length=80, blank=True)  # realtime/batch/hourly/daily...
    interface_name = models.CharField(max_length=120, blank=True)  # např. "Payments API v2"

    def __str__(self):
        return f"{self.source_app.name} -> {self.target_app.name}"


class TechDebtItem(models.Model):
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="tech_debt_items"
    )

    category = models.CharField(max_length=80)  # Security, Upgrade, CodeQuality, Performance...
    severity = models.CharField(max_length=30)  # Low/Medium/High/Critical
    status = models.CharField(max_length=30, default="Open")  # Open/InProgress/Done/WontFix

    title = models.CharField(max_length=140)
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    target_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.application.name}: {self.title}"