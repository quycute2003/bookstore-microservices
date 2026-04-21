from abc import ABC, abstractmethod
from typing import List, Optional
from ..entities.revenue_report import RevenueReport

class ReportRepository(ABC):
    @abstractmethod
    def find_all(self) -> List[RevenueReport]: ...

    @abstractmethod
    def find_by_id(self, id: int) -> Optional[RevenueReport]: ...

    @abstractmethod
    def save(self, report: RevenueReport) -> RevenueReport: ...
