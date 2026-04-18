"""Backward-compatible metadata entrypoint for platform context discovery."""

from __future__ import annotations

from .metadata import discover_platform_context

__all__ = ["discover_platform_context"]

