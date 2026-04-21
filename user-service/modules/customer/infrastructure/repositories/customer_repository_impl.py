from typing import List, Optional
from ...domain.entities.customer import Customer
from ...domain.value_objects.email import Email
from ...domain.repositories.customer_repository import CustomerRepository
from ..models.customer_model import CustomerModel


def _to_entity(m: CustomerModel) -> Customer:
    return Customer(id=m.id, name=m.name, email=Email(m.email))


class CustomerRepositoryImpl(CustomerRepository):
    def find_all(self) -> List[Customer]:
        return [_to_entity(m) for m in CustomerModel.objects.all()]

    def find_by_id(self, id: int) -> Optional[Customer]:
        try:
            return _to_entity(CustomerModel.objects.get(pk=id))
        except CustomerModel.DoesNotExist:
            return None

    def find_by_email(self, email: str) -> Optional[Customer]:
        try:
            return _to_entity(CustomerModel.objects.get(email=email))
        except CustomerModel.DoesNotExist:
            return None

    def save(self, customer: Customer) -> Customer:
        if customer.id:
            m = CustomerModel.objects.get(pk=customer.id)
            m.name  = customer.name
            m.email = str(customer.email)
            m.save()
        else:
            m = CustomerModel.objects.create(
                name=customer.name, email=str(customer.email)
            )
        return _to_entity(m)

    def delete(self, id: int) -> None:
        CustomerModel.objects.filter(pk=id).delete()
