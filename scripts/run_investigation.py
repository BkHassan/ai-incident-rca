#!/usr/bin/env python3
"""Run a live RCA for four representative incidents.

Uses GEMINI_API_KEY from the environment or .env, and the local Chroma store.
Prints hypotheses only. It does not read evaluation labels.

    python scripts/run_investigation.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from investigation import (  # noqa: E402
    ConfigurationError,
    InvestigationError,
    VectorStoreMissing,
    build_default_service,
)

CASES = ("INC-011", "INC-010", "INC-002", "INC-014")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "incidents",
        nargs="*",
        default=list(CASES),
        help="Incident ids to investigate. Default: the four representative cases.",
    )
    args = parser.parse_args(argv)
    try:
        service = build_default_service(load_env=True)
    except ConfigurationError as exc:
        print(f"Live investigation skipped: {exc.detail}")
        return 1
    except VectorStoreMissing as exc:
        print(f"Live investigation skipped: {exc.detail}")
        return 1
    try:
        for incident_id in args.incidents:
            result = service.investigate(incident_id)
            print("=" * 72)
            print(incident_id)
            print(f"  root cause: {result.root_cause.cause}")
            print(f"  confidence: {result.confidence:.2f} (uncalibrated)")
            ids = ", ".join(result.root_cause.supporting_evidence_ids) or "(none)"
            print(f"  supporting: {ids}")
            against = ", ".join(result.root_cause.contradicting_evidence_ids) or "(none)"
            print(f"  contradicting: {against}")
            if result.alternative_causes:
                print("  alternatives:")
                for item in result.alternative_causes:
                    print(f"    - {item.cause} ({item.confidence:.2f})")
            else:
                print("  alternatives: (none)")
            print()
    except InvestigationError as exc:
        print(f"Live investigation failed: {exc.code}: {exc.detail}", file=sys.stderr)
        return 1
    finally:
        closer = getattr(service, "retriever", None)
        if closer is not None and hasattr(closer, "close"):
            closer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
