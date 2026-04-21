from django.db import models

class RevenueReportModel(models.Model):
    report_name   = models.CharField(max_length=255, default="Báo cáo ngày")
    total_orders  = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    generated_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table  = 'revenue_reports'
        app_label = 'admin_infrastructure_models'
