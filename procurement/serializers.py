from rest_framework import serializers


class NotifySupplierProductRequestSerializer(serializers.Serializer):
    product_name = serializers.CharField(required=True)
    cost = serializers.DecimalField(max_digits=12, decimal_places=2)


class NotifySupplierProductResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
