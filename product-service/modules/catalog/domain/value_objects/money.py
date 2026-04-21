"""
Value Object: Money
===================
Bất biến (immutable). Encapsulate giá tiền + đơn vị.
"""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "VND"

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("Giá tiền không thể âm")

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("Không thể cộng hai đơn vị tiền tệ khác nhau")
        return Money(self.amount + other.amount, self.currency)

    def formatted(self) -> str:
        return f"{int(self.amount):,}".replace(",", ".") + f" {self.currency}"
