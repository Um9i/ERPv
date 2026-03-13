"""Shared admin utilities used by multiple apps."""

from __future__ import annotations

from typing import Any


class NoDeleteActionMixin:
    """Admin mixin that removes the built-in 'delete_selected' action."""

    def get_actions(self, request: Any) -> dict[str, Any]:
        actions: dict[str, Any] = super().get_actions(request)  # type: ignore[misc]
        actions.pop("delete_selected", None)
        return actions
