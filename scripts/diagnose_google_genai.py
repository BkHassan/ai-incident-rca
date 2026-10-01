#!/usr/bin/env python3
"""Temporary Google GenAI access diagnostic. Does not change project models or architecture.

    python scripts/diagnose_google_genai.py

Loads GEMINI_API_KEY / GOOGLE_API_KEY from .env the same way as the rest of the project.
Never prints credentials or embedding vectors.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402
from retrieval.embeddings import DEFAULT_DIMENSIONS, DEFAULT_EMBEDDING_MODEL  # noqa: E402

DEFAULT_GENAI_MODEL = "gemini-2.5-flash"
_OPTIONAL_GEN_PROBE = "gemini-3.8-flash"
_OPTIONAL_EMBEDDING_PROBE = "gemini-embedding-2"
_KEY_RE = re.compile(r"(?:AIza|AQ\.)[\w\-]+")


def _api_key() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def _public_error(exc: BaseException, api_key: str) -> tuple[str, str]:
    text = str(exc)
    if api_key:
        text = text.replace(api_key, "[redacted]")
    text = _KEY_RE.sub("[redacted]", text)
    if "api_key" in text.lower() or "api key" in text.lower():
        text = "The Gemini request failed. Check GENAI_MODEL and credentials."
    return type(exc).__name__, text[:500]


def _client(api_key: str):
    return genai.Client(api_key=api_key)


def test_generation(client, model: str, api_key: str) -> dict:
    result = {"status": "FAIL", "model": model, "error_type": "", "error_message": ""}
    try:
        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly: GENAI_OK",
        )
        text = (getattr(response, "text", None) or "").strip()
        if "GENAI_OK" in text:
            result["status"] = "PASS"
        else:
            result["error_type"] = "UnexpectedResponse"
            result["error_message"] = "model response did not contain GENAI_OK"
    except Exception as exc:
        result["error_type"], result["error_message"] = _public_error(exc, api_key)
    return result


def test_embedding(client, model: str, api_key: str, *, use_task_type: bool) -> dict:
    result = {
        "status": "FAIL",
        "model": model,
        "dimension": "",
        "error_type": "",
        "error_message": "",
    }
    try:
        kwargs = {"output_dimensionality": DEFAULT_DIMENSIONS}
        if use_task_type:
            kwargs["task_type"] = "RETRIEVAL_DOCUMENT"
        response = client.models.embed_content(
            model=model,
            contents="test incident database connection failure",
            config=types.EmbedContentConfig(**kwargs),
        )
        embeddings = list(response.embeddings or [])
        if not embeddings or not getattr(embeddings[0], "values", None):
            result["error_type"] = "EmptyEmbedding"
            result["error_message"] = "embedding API returned no vector"
            return result
        result["status"] = "PASS"
        result["dimension"] = str(len(list(embeddings[0].values)))
    except Exception as exc:
        result["error_type"], result["error_message"] = _public_error(exc, api_key)
    return result


def main() -> int:
    api_key = _api_key()
    print("API key:", "PRESENT" if api_key else "MISSING")
    if not api_key:
        print("Generation: FAIL")
        print("Model: (not called)")
        print("Error type: ConfigurationError")
        print("Error message: Set GEMINI_API_KEY or GOOGLE_API_KEY.")
        print("Embedding: FAIL")
        print("Model: (not called)")
        print("Embedding dimension:")
        print("Error type: ConfigurationError")
        print("Error message: Set GEMINI_API_KEY or GOOGLE_API_KEY.")
        return 1

    gen_model = os.environ.get("GENAI_MODEL", DEFAULT_GENAI_MODEL)
    embed_model = os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
    client = _client(api_key)

    generation = test_generation(client, gen_model, api_key)
    print("Generation:", generation["status"])
    print("Model:", generation["model"])
    print("Error type:", generation["error_type"] or "(none)")
    print("Error message:", generation["error_message"] or "(none)")

    configured = test_embedding(
        client, embed_model, api_key, use_task_type="embedding-2" not in embed_model
    )
    print("Embedding:", configured["status"])
    print("Model:", configured["model"])
    print("Embedding dimension:", configured["dimension"] or "(none)")
    print("Error type:", configured["error_type"] or "(none)")
    print("Error message:", configured["error_message"] or "(none)")

    if generation["status"] != "PASS" and gen_model != _OPTIONAL_GEN_PROBE:
        probe_gen = test_generation(client, _OPTIONAL_GEN_PROBE, api_key)
        print("Optional generation probe:", probe_gen["status"])
        print("Optional generation probe model:", probe_gen["model"])
        print("Optional generation probe error type:", probe_gen["error_type"] or "(none)")
        print("Optional generation probe error message:", probe_gen["error_message"] or "(none)")

    if configured["status"] != "PASS" and embed_model != _OPTIONAL_EMBEDDING_PROBE:
        probe = test_embedding(client, _OPTIONAL_EMBEDDING_PROBE, api_key, use_task_type=False)
        print("Optional embedding probe:", probe["status"])
        print("Optional probe model:", probe["model"])
        print("Optional probe dimension:", probe["dimension"] or "(none)")
        print("Optional probe error type:", probe["error_type"] or "(none)")
        print("Optional probe error message:", probe["error_message"] or "(none)")
    return 0 if generation["status"] == "PASS" and configured["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
