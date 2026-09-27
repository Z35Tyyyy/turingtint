"""Bounded, local verification and evidence tracking for detector development."""

from .runner import ProtocolError, run, status

__all__ = ["ProtocolError", "run", "status"]
