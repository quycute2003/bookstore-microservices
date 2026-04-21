import requests
from typing import List
from ...domain.entities.staff import Staff
from ...domain.repositories.staff_repository import StaffRepository
from ..commands import CreateStaffCommand, UpdateStaffCommand

PRODUCT_SERVICE_URL = "http://product-service:8000"


class StaffNotFound(Exception):
    pass


class StaffService:
    def __init__(self, repo: StaffRepository):
        self._repo = repo

    def list_staffs(self) -> List[Staff]:
        return self._repo.find_all()

    def get_staff(self, id: int) -> Staff:
        staff = self._repo.find_by_id(id)
        if not staff:
            raise StaffNotFound(f"Không tìm thấy nhân viên id={id}")
        return staff

    def create_staff(self, cmd: CreateStaffCommand) -> Staff:
        staff = Staff.create(cmd.name, cmd.email, cmd.department)
        return self._repo.save(staff)

    def update_staff(self, id: int, cmd: UpdateStaffCommand) -> Staff:
        staff = self.get_staff(id)
        staff.update(name=cmd.name, email=cmd.email, department=cmd.department)
        return self._repo.save(staff)

    def delete_staff(self, id: int) -> None:
        self.get_staff(id)
        self._repo.delete(id)

    def add_product(self, staff_id: int, product_data: dict) -> dict:
        """Nhân viên nhập sản phẩm vào kho qua product-service."""
        self.get_staff(staff_id)  # xác nhận nhân viên tồn tại
        product_type = product_data.get("product_type", "book")
        endpoint = "books" if product_type == "book" else "clothes"
        res = requests.post(
            f"{PRODUCT_SERVICE_URL}/{endpoint}/",
            json=product_data, timeout=5
        )
        if res.status_code in (200, 201):
            return res.json()
        raise RuntimeError(f"Lỗi khi thêm sản phẩm: {res.text}")
