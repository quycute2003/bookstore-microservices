from dataclasses import dataclass
from typing import Optional

@dataclass
class ListCustomersQuery:
    pass

@dataclass
class GetCustomerQuery:
    id: int
