from rest_framework import serializers
from .models import Inventory


class InventorySerializer(serializers.ModelSerializer):
    product = serializers.StringRelatedField()
    class Meta:
        model = Inventory
        fields = ["product", "quantity"]
