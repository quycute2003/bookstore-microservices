from typing import List, Optional
from ...domain.entities.revenue_report import RevenueReport
from ...domain.repositories.report_repository import ReportRepository
from ..models.report_model import RevenueReportModel


def _to_entity(m: RevenueReportModel) -> RevenueReport:
    return RevenueReport(
        id=m.id,
        report_name=m.report_name,
        total_orders=m.total_orders,
        total_revenue=float(m.total_revenue),
        generated_at=m.generated_at,
    )


class ReportRepositoryImpl(ReportRepository):
    def find_all(self) -> List[RevenueReport]:
        return [_to_entity(m) for m in RevenueReportModel.objects.order_by('-generated_at')]

    def find_by_id(self, id: int) -> Optional[RevenueReport]:
        try:
            return _to_entity(RevenueReportModel.objects.get(pk=id))
        except RevenueReportModel.DoesNotExist:
            return None

    def save(self, report: RevenueReport) -> RevenueReport:
        m = RevenueReportModel.objects.create(
            report_name=report.report_name,
            total_orders=report.total_orders,
            total_revenue=report.total_revenue,
        )
        return _to_entity(m)
