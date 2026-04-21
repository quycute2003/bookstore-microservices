from rest_framework import serializers
from ....application.commands import CreateCustomerCommand, UpdateCustomerCommand


class CustomerInputSerializer(serializers.Serializer):
    name  = serializers.CharField(max_length=255)
    email = serializers.EmailField()

    def to_command(self) -> CreateCustomerCommand:
        return CreateCustomerCommand(**self.validated_data)


class CustomerUpdateSerializer(serializers.Serializer):
    name  = serializers.CharField(max_length=255, required=False)
    email = serializers.EmailField(required=False)

    def to_command(self) -> UpdateCustomerCommand:
        return UpdateCustomerCommand(**self.validated_data)


class CustomerOutputSerializer(serializers.Serializer):
    id    = serializers.IntegerField()
    name  = serializers.CharField()
    email = serializers.SerializerMethodField()

    def get_email(self, obj):
        return str(obj.email)
