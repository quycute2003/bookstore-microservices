from dataclasses import dataclass
from typing import Optional

@dataclass
class CreateCustomerCommand:
    name: str
    email: str

@dataclass
class UpdateCustomerCommand:
    name: Optional[str] = None
    email: Optional[str] = None
