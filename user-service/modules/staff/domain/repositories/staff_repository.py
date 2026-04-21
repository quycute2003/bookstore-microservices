from abc import ABC, abstractmethod
from typing import List, Optional
from ..entities.staff import Staff

class StaffRepository(ABC):
    @abstractmethod
    def find_all(self) -> List[Staff]: ...

    @abstractmethod
    def find_by_id(self, id: int) -> Optional[Staff]: ...

    @abstractmethod
    def save(self, staff: Staff) -> Staff: ...

    @abstractmethod
    def delete(self, id: int) -> None: ...
