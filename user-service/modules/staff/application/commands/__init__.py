from dataclasses import dataclass
from typing import Optional

@dataclass
class CreateStaffCommand:
    name: str
    email: str
    department: str = 'Catalog'

@dataclass
class UpdateStaffCommand:
    name: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
