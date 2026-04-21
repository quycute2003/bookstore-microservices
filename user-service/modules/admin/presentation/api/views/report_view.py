from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ....application.services.report_service import ReportService, ReportNotFound
from ....infrastructure.repositories.report_repository_impl import ReportRepositoryImpl
from ..serializers.report_serializer import GenerateReportInputSerializer, ReportOutputSerializer


def _service() -> ReportService:
    return ReportService(ReportRepositoryImpl())


class ReportListCreateView(APIView):
    def get(self, request):
        reports = _service().list_reports()
        return Response(ReportOutputSerializer(reports, many=True).data)

    def post(self, request):
        ser = GenerateReportInputSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            report = _service().generate_report(ser.to_command())
            return Response(
                {"message": "Sếp ơi, báo cáo đã sẵn sàng!", "data": ReportOutputSerializer(report).data},
                status=status.HTTP_201_CREATED
            )
        except RuntimeError as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)


class ReportDetailView(APIView):
    def get(self, request, pk):
        try:
            report = _service().get_report(pk)
            return Response(ReportOutputSerializer(report).data)
        except ReportNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
