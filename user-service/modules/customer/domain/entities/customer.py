from dataclasses import dataclass, field
from typing import Optional
from ..value_objects.email import Email

@dataclass
class Customer:
    id: Optional[int]
    name: str
    email: Email

    @classmethod
    def create(cls, name: str, email_str: str) -> 'Customer':
        if not name or not name.strip():
            raise ValueError("Tên khách hàng không được để trống")
        return cls(id=None, name=name.strip(), email=Email(email_str))

    def update(self, name: str = None, email_str: str = None):
        if name is not None:
            if not name.strip():
                raise ValueError("Tên không được để trống")
            self.name = name.strip()
        if email_str is not None:
            self.email = Email(email_str)
