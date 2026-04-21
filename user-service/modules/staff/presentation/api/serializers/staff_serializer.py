from rest_framework import serializers
from ....application.commands import CreateStaffCommand, UpdateStaffCommand


class StaffInputSerializer(serializers.Serializer):
    name       = serializers.CharField(max_length=255)
    email      = serializers.EmailField()
    department = serializers.CharField(max_length=100, default='Catalog')

    def to_command(self) -> CreateStaffCommand:
        return CreateStaffCommand(**self.validated_data)


class StaffUpdateSerializer(serializers.Serializer):
    name       = serializers.CharField(max_length=255, required=False)
    email      = serializers.EmailField(required=False)
    department = serializers.CharField(max_length=100, required=False)

    def to_command(self) -> UpdateStaffCommand:
        return UpdateStaffCommand(**self.validated_data)


class StaffOutputSerializer(serializers.Serializer):
    id         = serializers.IntegerField()
    name       = serializers.CharField()
    email      = serializers.CharField()
    department = serializers.CharField()
