from rest_framework import serializers


class PurchaseOrderLineSerializer(serializers.Serializer):
    product_name = serializers.CharField(required=True)
    quantity = serializers.IntegerField(required=True)


class NotifyPurchaseOrderRequestSerializer(serializers.Serializer):
    lines = PurchaseOrderLineSerializer(many=True)
    due_date = serializers.DateField(required=False, allow_null=True, default=None)
    order_number = serializers.CharField(required=False, default="")


class NotifyPurchaseOrderResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    sales_order = serializers.CharField()
    skipped_products = serializers.ListField(child=serializers.CharField())
