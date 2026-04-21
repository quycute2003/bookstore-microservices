from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ....application.services.staff_service import StaffService, StaffNotFound
from ....infrastructure.repositories.staff_repository_impl import StaffRepositoryImpl
from ..serializers.staff_serializer import (
    StaffInputSerializer, StaffUpdateSerializer, StaffOutputSerializer
)


def _service() -> StaffService:
    return StaffService(StaffRepositoryImpl())


class StaffListCreateView(APIView):
    def get(self, request):
        staffs = _service().list_staffs()
        return Response(StaffOutputSerializer(staffs, many=True).data)

    def post(self, request):
        ser = StaffInputSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            staff = _service().create_staff(ser.to_command())
            return Response(StaffOutputSerializer(staff).data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StaffDetailView(APIView):
    def get(self, request, pk):
        try:
            return Response(StaffOutputSerializer(_service().get_staff(pk)).data)
        except StaffNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        ser = StaffUpdateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            staff = _service().update_staff(pk, ser.to_command())
            return Response(StaffOutputSerializer(staff).data)
        except StaffNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            _service().delete_staff(pk)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except StaffNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)


class StaffAddProductView(APIView):
    """Nhân viên nhập sản phẩm vào kho — proxy sang product-service."""
    def post(self, request, pk):
        try:
            result = _service().add_product(pk, request.data)
            return Response({"message": f"Đã thêm sản phẩm thành công!", "product": result},
                            status=status.HTTP_201_CREATED)
        except StaffNotFound as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except RuntimeError as e:
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
