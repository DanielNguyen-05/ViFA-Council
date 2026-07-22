"""Backward-compatible outpainting Council entry point."""

from .council import StructuredCouncil


class OutpaintingCouncil(StructuredCouncil):
    def __init__(self, **kwargs):
        super().__init__("outpainting", **kwargs)
