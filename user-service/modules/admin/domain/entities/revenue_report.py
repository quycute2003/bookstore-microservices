from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

@dataclass
class RevenueReport:
    id: Optional[int]
    report_name: str
    total_orders: int
    total_revenue: float
    generated_at: Optional[datetime] = None

    @classmethod
    def create(cls, report_name: str, total_orders: int, total_revenue: float) -> 'RevenueReport':
        return cls(
            id=None,
            report_name=report_name,
            total_orders=total_orders,
            total_revenue=round(total_revenue, 2),
        )
