"""Structured phishing-detection result produced by PhishWalk."""

from pydantic import BaseModel, ConfigDict, Field


class DetectionResult(BaseModel):
    """Final phishing verdict for the observed URL."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(
        description=(
            "Initial target URL submitted for detection, even if interaction "
            "later navigates or redirects to another URL."
        ),
    )
    is_phishing: bool = Field(
        description="Whether the observed website is classified as phishing.",
    )
    reason: str = Field(
        min_length=1,
        description="Concise reason grounded in the observed evidence.",
    )
