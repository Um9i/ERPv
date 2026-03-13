"""Shared form validators and field definitions."""

from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r"^\+?[\d\s\-().]{7,64}$",
    message="Enter a valid phone number (digits, spaces, dashes, parentheses).",
)
