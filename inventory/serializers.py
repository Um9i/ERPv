from rest_framework import serializers


class CatalogueItemSerializer(serializers.Serializer):
    name = serializers.CharField()
    description = serializers.CharField()
    sale_price = serializers.SerializerMethodField()
    sku = serializers.SerializerMethodField()

    def get_sale_price(self, obj):
        return f"{obj.sale_price:.2f}"

    def get_sku(self, obj):
        return None
