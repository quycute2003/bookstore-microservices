from abc import ABC, abstractmethod
from typing import List, Optional
from ..entities.customer import Customer

class CustomerRepository(ABC):
    @abstractmethod
    def find_all(self) -> List[Customer]: ...

    @abstractmethod
    def find_by_id(self, id: int) -> Optional[Customer]: ...

    @abstractmethod
    def find_by_email(self, email: str) -> Optional[Customer]: ...

    @abstractmethod
    def save(self, customer: Customer) -> Customer: ...

    @abstractmethod
    def delete(self, id: int) -> None: ...
