"""RCA investigation: context, prompt, Gemini, and evidence checks.

    from investigation import build_investigation_context, InvestigationService
"""

from .context_builder import build_investigation_context
from .evidence import insufficient_result, validate_rca
from .investigator import (
    DEFAULT_GENAI_MODEL,
    GeminiInvestigator,
    InvestigationService,
    Settings,
    build_default_service,
    load_settings,
)
from .models import (
    INSUFFICIENT_EVIDENCE,
    ConfigurationError,
    IncidentNotFound,
    InvalidRCA,
    InvestigationContext,
    InvestigationError,
    InvestigationFailed,
    RCAResult,
    RetrievalFailed,
    VectorStoreMissing,
)
from .prompt import render_prompt

__all__ = [
    "build_investigation_context", "render_prompt", "validate_rca", "insufficient_result",
    "GeminiInvestigator", "InvestigationService", "Settings", "build_default_service", "load_settings",
    "RCAResult", "InvestigationContext", "INSUFFICIENT_EVIDENCE", "DEFAULT_GENAI_MODEL",
    "IncidentNotFound", "ConfigurationError", "VectorStoreMissing", "RetrievalFailed",
    "InvestigationError", "InvestigationFailed", "InvalidRCA",
]
