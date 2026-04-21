from rest_framework import serializers
from ....application.commands import GenerateReportCommand


class GenerateReportInputSerializer(serializers.Serializer):
    report_name = serializers.CharField(
        max_length=255, default="Báo cáo Doanh thu Tự động", required=False
    )

    def to_command(self) -> GenerateReportCommand:
        return GenerateReportCommand(**self.validated_data)


class ReportOutputSerializer(serializers.Serializer):
    id            = serializers.IntegerField()
    report_name   = serializers.CharField()
    total_orders  = serializers.IntegerField()
    total_revenue = serializers.FloatField()
    generated_at  = serializers.DateTimeField()
