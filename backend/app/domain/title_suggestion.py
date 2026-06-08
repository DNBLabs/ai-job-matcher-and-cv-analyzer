"""Domain schemas for sync AI Suggested Job Titles."""

from pydantic import BaseModel, Field


class SuggestedTitle(BaseModel):
    """One AI-generated job title recommendation with supporting rationale."""

    title: str = Field(..., min_length=1, max_length=200)
    rationale: str = Field(..., min_length=1, max_length=500)


class TitleSuggestionsLlmOutput(BaseModel):
    """Structured LLM payload validated before returning API responses."""

    titles: list[SuggestedTitle]


class TitleSuggestionResponse(BaseModel):
    """Public API response for POST /cvs/{id}/suggest-titles."""

    titles: list[SuggestedTitle]
