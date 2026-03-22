from rest_framework import serializers


class CompanySerializer(serializers.Serializer):
    name = serializers.CharField()
    address_line_1 = serializers.CharField()
    address_line_2 = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    postal_code = serializers.CharField()
    country = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.CharField()
    website = serializers.CharField()
    vat_number = serializers.CharField()
    company_number = serializers.CharField()


class NotifyCustomerRequestSerializer(serializers.Serializer):
    name = serializers.CharField(required=True)
    address_line_1 = serializers.CharField(required=False, default="")
    address_line_2 = serializers.CharField(required=False, default="")
    city = serializers.CharField(required=False, default="")
    state = serializers.CharField(required=False, default="")
    postal_code = serializers.CharField(required=False, default="")
    country = serializers.CharField(required=False, default="")
    phone = serializers.CharField(required=False, default="")
    email = serializers.CharField(required=False, default="")
    website = serializers.CharField(required=False, default="")


class NotifyCustomerResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    created = serializers.BooleanField()


class NotifyCustomerProductRequestSerializer(serializers.Serializer):
    product_name = serializers.CharField(required=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2)


class NotifyCustomerProductResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    created = serializers.BooleanField()
