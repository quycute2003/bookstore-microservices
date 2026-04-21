from dataclasses import dataclass
import re

@dataclass(frozen=True)
class Email:
    value: str

    def __post_init__(self):
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', self.value):
            raise ValueError(f"Email không hợp lệ: {self.value}")

    def __str__(self):
        return self.value
