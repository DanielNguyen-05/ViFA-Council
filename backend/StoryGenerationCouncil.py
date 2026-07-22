"""Educational story-generation Council entry point."""

from .council import StructuredCouncil


class StoryGenerationCouncil(StructuredCouncil):
    def __init__(self, **kwargs):
        super().__init__("story_generation", **kwargs)
