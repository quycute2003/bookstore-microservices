import requests
from typing import List
from ...domain.entities.revenue_report import RevenueReport
from ...domain.repositories.report_repository import ReportRepository
from ..commands import GenerateReportCommand

ORDER_SERVICE_URL = "http://order-service:8000"


class ReportNotFound(Exception):
    pass


class ReportService:
    def __init__(self, repo: ReportRepository):
        self._repo = repo

    def list_reports(self) -> List[RevenueReport]:
        return self._repo.find_all()

    def get_report(self, id: int) -> RevenueReport:
        report = self._repo.find_by_id(id)
        if not report:
            raise ReportNotFound(f"Không tìm thấy báo cáo id={id}")
        return report

    def generate_report(self, cmd: GenerateReportCommand) -> RevenueReport:
        """Kéo dữ liệu từ order-service, tính doanh thu, lưu báo cáo."""
        try:
            res = requests.get(f"{ORDER_SERVICE_URL}/orders/", timeout=5)
            if res.status_code != 200:
                raise RuntimeError("Không kết nối được order-service")
            orders = res.json()
        except Exception as e:
            raise RuntimeError(f"Order Service lỗi: {e}")

        paid_orders = [o for o in orders if o.get('status') == 'PAID_AND_SHIPPING']
        total_orders   = len(paid_orders)
        total_revenue  = sum(float(o.get('total_price', 0)) for o in paid_orders)

        report = RevenueReport.create(cmd.report_name, total_orders, total_revenue)
        return self._repo.save(report)
