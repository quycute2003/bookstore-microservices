from dataclasses import dataclass
from typing import Optional

@dataclass
class Staff:
    id: Optional[int]
    name: str
    email: str
    department: str

    @classmethod
    def create(cls, name: str, email: str, department: str = 'Catalog') -> 'Staff':
        if not name or not name.strip():
            raise ValueError("Tên nhân viên không được để trống")
        return cls(id=None, name=name.strip(), email=email, department=department)

    def update(self, name: str = None, email: str = None, department: str = None):
        if name is not None:
            self.name = name.strip()
        if email is not None:
            self.email = email
        if department is not None:
            self.department = department
