from typing import List, Optional
from ...domain.entities.staff import Staff
from ...domain.repositories.staff_repository import StaffRepository
from ..models.staff_model import StaffModel


def _to_entity(m: StaffModel) -> Staff:
    return Staff(id=m.id, name=m.name, email=m.email, department=m.department)


class StaffRepositoryImpl(StaffRepository):
    def find_all(self) -> List[Staff]:
        return [_to_entity(m) for m in StaffModel.objects.all()]

    def find_by_id(self, id: int) -> Optional[Staff]:
        try:
            return _to_entity(StaffModel.objects.get(pk=id))
        except StaffModel.DoesNotExist:
            return None

    def save(self, staff: Staff) -> Staff:
        if staff.id:
            m = StaffModel.objects.get(pk=staff.id)
            m.name = staff.name; m.email = staff.email; m.department = staff.department
            m.save()
        else:
            m = StaffModel.objects.create(
                name=staff.name, email=staff.email, department=staff.department
            )
        return _to_entity(m)

    def delete(self, id: int) -> None:
        StaffModel.objects.filter(pk=id).delete()
