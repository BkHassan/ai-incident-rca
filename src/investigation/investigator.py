"""Call Gemini for an RCA, then validate evidence ids.

Unit tests inject a client. The live client is created only when an API key is present.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import ValidationError

from ingestion import DEFAULT_DATA_DIR
from retrieval.embeddings import DEFAULT_EMBEDDING_MODEL, GeminiEmbeddingProvider
from retrieval.indexer import default_vectorstore
from retrieval.models import RetrievalError
from retrieval.retriever import Retriever

from .context_builder import build_investigation_context
from .evidence import insufficient_result, validate_rca
from .models import (
    ConfigurationError,
    IncidentNotFound,
    InvalidRCA,
    InvestigationContext,
    InvestigationFailed,
    RCAResult,
    RetrievalFailed,
    VectorStoreMissing,
)
from .prompt import render_prompt

DEFAULT_GENAI_MODEL = "gemini-2.5-flash"
_KEY_RE = re.compile(r"(?:AIza|AQ\.)[\w\-]+")


class Settings:
    """Process configuration. The API key is never written to disk by this object."""

    def __init__(
        self,
        api_key: str = "",
        model: str = DEFAULT_GENAI_MODEL,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        chroma_path: Path | None = None,
        data_dir: Path | None = None,
        max_attempts: int = 2,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.embedding_model = embedding_model
        self.chroma_path = chroma_path or default_vectorstore(_repo_root())
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.max_attempts = max(1, max_attempts)


def load_settings(load_env_file: bool = True) -> Settings:
    if load_env_file:
        from dotenv import load_dotenv

        load_dotenv(_repo_root() / ".env")
    raw_attempts = os.environ.get("GENAI_MAX_ATTEMPTS", "2")
    try:
        attempts = int(raw_attempts)
    except ValueError:
        attempts = 2
    chroma = os.environ.get("CHROMA_PATH")
    if chroma:
        chroma_path = Path(chroma)
        if not chroma_path.is_absolute():
            chroma_path = _repo_root() / chroma_path
    else:
        chroma_path = default_vectorstore(_repo_root())
    return Settings(
        api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "",
        model=os.environ.get("GENAI_MODEL", DEFAULT_GENAI_MODEL),
        embedding_model=os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        chroma_path=chroma_path,
        data_dir=DEFAULT_DATA_DIR,
        max_attempts=attempts,
    )


def chroma_ready(path: Path) -> bool:
    return (path / "chroma.sqlite3").is_file()


class GeminiInvestigator:
    """Structured-output investigator. Retries a small number of times on invalid RCA JSON."""

    def __init__(self, settings: Settings, client=None) -> None:
        self.settings = settings
        self._client = client

    def investigate(self, context: InvestigationContext) -> RCAResult:
        if not context.evidence:
            return insufficient_result(
                context.incident_id,
                "No anomaly, log, historical, or technical evidence was supplied.",
            )
        prompt = render_prompt(context)
        last_error = "the model returned no valid RCA"
        for _ in range(self.settings.max_attempts):
            try:
                raw = self._generate(prompt)
                draft = _parse_rca(raw)
                return validate_rca(draft, context)
            except InvalidRCA as exc:
                last_error = exc.detail
            except ValidationError as exc:
                last_error = f"structured output did not match the RCA schema ({exc.error_count()} errors)"
            except InvestigationFailed:
                raise
        raise InvalidRCA(f"Gemini output was rejected after {self.settings.max_attempts} attempts: {last_error}")

    def _generate(self, prompt: str):
        from google.genai import types

        try:
            response = self._client_or_create().models.generate_content(
                model=self.settings.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=RCAResult,
                ),
            )
        except InvalidRCA:
            raise
        except Exception as exc:
            raise InvestigationFailed(_public_message(exc, self.settings.api_key)) from exc
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return parsed
        text = getattr(response, "text", None)
        if not text:
            raise InvalidRCA("Gemini returned an empty response")
        return text

    def _client_or_create(self):
        if self._client is not None:
            return self._client
        if not self.settings.api_key:
            raise ConfigurationError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")
        from google import genai

        self._client = genai.Client(api_key=self.settings.api_key)
        return self._client


class InvestigationService:
    """Load evidence, retrieve, investigate, and validate. Routes call this, not the prompt."""

    def __init__(self, settings: Settings, investigator: GeminiInvestigator, retriever, data_dir: Path) -> None:
        self.settings = settings
        self.investigator = investigator
        self.retriever = retriever
        self.data_dir = data_dir

    def investigate(self, incident_id: str) -> RCAResult:
        from ingestion import incident_path

        if not incident_path(incident_id, self.data_dir).is_file():
            raise IncidentNotFound(f"No incident {incident_id}")
        try:
            retrieval = self.retriever.retrieve_incident(incident_id, self.data_dir)
        except RetrievalError as exc:
            raise RetrievalFailed(_public_message(exc, self.settings.api_key)) from exc
        context = build_investigation_context(incident_id, self.data_dir, retrieval)
        return self.investigator.investigate(context)


def build_default_service(settings: Settings | None = None, *, load_env: bool = True) -> InvestigationService:
    settings = settings or load_settings(load_env)
    if not settings.api_key:
        raise ConfigurationError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")
    if not chroma_ready(settings.chroma_path):
        raise VectorStoreMissing(
            f"Chroma store not found at {settings.chroma_path}. Run scripts/build_vector_index.py."
        )
    embedder = GeminiEmbeddingProvider(model=settings.embedding_model, api_key=settings.api_key)
    retriever = Retriever(settings.chroma_path, embedder)
    return InvestigationService(
        settings,
        GeminiInvestigator(settings),
        retriever,
        settings.data_dir,
    )


def _parse_rca(raw) -> RCAResult:
    if isinstance(raw, RCAResult):
        return raw
    if isinstance(raw, dict):
        return RCAResult.model_validate(raw)
    if isinstance(raw, str):
        return RCAResult.model_validate_json(raw)
    if hasattr(raw, "model_dump"):
        return RCAResult.model_validate(raw.model_dump())
    raise InvalidRCA("Gemini returned an unsupported payload")


def _public_message(exc: Exception, api_key: str = "") -> str:
    text = str(exc)
    if api_key:
        text = text.replace(api_key, "[redacted]")
    text = _KEY_RE.sub("[redacted]", text)
    if "api_key" in text.lower() or "api key" in text.lower():
        return "The Gemini request failed. Check GENAI_MODEL and credentials."
    return text[:500]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]
