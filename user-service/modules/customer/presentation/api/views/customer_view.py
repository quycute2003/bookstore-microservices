from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ....application.services.customer_service import CustomerService, CustomerNotFound
from ....infrastructure.repositories.customer_repository_impl import CustomerRepositoryImpl
from ..serializers.customer_serializer import (
    CustomerInputSerializer, CustomerUpdateSerializer, CustomerOutputSerializer
)


def _service() -> CustomerService:
    return CustomerService(CustomerRepositoryImpl())


class CustomerListCreateView(APIView):
    def get(self, request):
        customers = _service().list_customers()
        return Response(CustomerOutputSerializer(customers, many=True).data)

    def post(self, request):
        ser = CustomerInputSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer = _service().create_customer(ser.to_command())
            return Response(CustomerOutputSerializer(customer).data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CustomerDetailView(APIView):
    def get(self, request, pk):
        try:
            customer = _service().get_customer(pk)
            return Response(CustomerOutputSerializer(customer).data)
        except CustomerNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        ser = CustomerUpdateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            customer = _service().update_customer(pk, ser.to_command())
            return Response(CustomerOutputSerializer(customer).data)
        except CustomerNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            _service().delete_customer(pk)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except CustomerNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
