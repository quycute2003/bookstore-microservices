import requests
from typing import List, Optional
from ...domain.entities.customer import Customer
from ...domain.repositories.customer_repository import CustomerRepository
from ..commands import CreateCustomerCommand, UpdateCustomerCommand

CART_SERVICE_URL = "http://cart-service:8000"


class CustomerNotFound(Exception):
    pass


class CustomerService:
    def __init__(self, repo: CustomerRepository):
        self._repo = repo

    def list_customers(self) -> List[Customer]:
        return self._repo.find_all()

    def get_customer(self, id: int) -> Customer:
        customer = self._repo.find_by_id(id)
        if not customer:
            raise CustomerNotFound(f"Không tìm thấy khách hàng id={id}")
        return customer

    def create_customer(self, cmd: CreateCustomerCommand) -> Customer:
        customer = Customer.create(cmd.name, cmd.email)
        saved = self._repo.save(customer)
        # Tự động tạo giỏ hàng cho khách mới
        try:
            requests.post(f"{CART_SERVICE_URL}/carts/",
                          json={"customer_id": saved.id}, timeout=3)
        except Exception:
            pass  # Cart service có thể chưa sẵn sàng — không chặn customer creation
        return saved

    def update_customer(self, id: int, cmd: UpdateCustomerCommand) -> Customer:
        customer = self.get_customer(id)
        customer.update(name=cmd.name, email_str=cmd.email)
        return self._repo.save(customer)

    def delete_customer(self, id: int) -> None:
        self.get_customer(id)
        self._repo.delete(id)
