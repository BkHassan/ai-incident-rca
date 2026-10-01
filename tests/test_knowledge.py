"""Checks on the historical knowledge base (Day 7).

    python -m unittest tests.test_knowledge
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_knowledge import (  # noqa: E402
    DB,
    DOWN,
    LABELS,
    MEM,
    generate,
)

KNOWLEDGE = ROOT / "knowledge" / "incidents"
EVAL_INCIDENTS = ROOT / "data" / "raw" / "incidents"
EVAL_CUTOFF = datetime(2026, 1, 8)
REQUIRED = {
    "incident_id",
    "title",
    "occurred_at",
    "service",
    "severity",
    "duration_minutes",
    "symptoms",
    "observed_signals",
    "timeline",
    "root_cause",
    "contributing_factors",
    "resolution",
    "lessons_learned",
    "tags",
}
KNOWN_SERVICES = {
    "api-gateway",
    "orders-api",
    "payment-api",
    "inventory-service",
    "recommendation-service",
    "database",
}
NARRATIVE = ("title", "symptoms", "observed_signals", "timeline", "tags")
FORBIDDEN = re.compile(
    r"DB_CONNECTION_POOL_EXHAUSTION|MEMORY_LEAK|DOWNSTREAM_SERVICE_TIMEOUT|"
    r"\bmemory leak\b|\bpool exhaust",
    re.IGNORECASE,
)


def load_all() -> list[dict]:
    paths = sorted(KNOWLEDGE.glob("HIST-*.json"))
    return [json.loads(p.read_text(encoding="utf-8")) for p in paths]


class KnowledgeCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_all()
        cls.by_id = {r["incident_id"]: r for r in cls.records}

    def test_exactly_thirty_hist_files(self):
        self.assertEqual(len(self.records), 30)
        self.assertEqual(
            [r["incident_id"] for r in self.records],
            [f"HIST-{i:03d}" for i in range(1, 31)],
        )

    def test_balanced_root_causes(self):
        counts = Counter(r["root_cause"] for r in self.records)
        self.assertEqual(counts[DB], 10)
        self.assertEqual(counts[MEM], 10)
        self.assertEqual(counts[DOWN], 10)

    def test_required_fields_and_nonempty_lists(self):
        for record in self.records:
            missing = REQUIRED - record.keys()
            self.assertFalse(missing, f"{record['incident_id']} missing {missing}")
            self.assertIn(record["root_cause"], LABELS)
            self.assertIn(record["severity"], {"LOW", "MEDIUM", "HIGH", "CRITICAL"})
            self.assertGreaterEqual(record["duration_minutes"], 10)
            self.assertGreaterEqual(len(record["symptoms"]), 3)
            self.assertGreaterEqual(len(record["observed_signals"]), 3)
            self.assertGreaterEqual(len(record["timeline"]), 3)
            self.assertGreaterEqual(len(record["contributing_factors"]), 1)
            self.assertGreaterEqual(len(record["resolution"]), 1)
            self.assertGreaterEqual(len(record["lessons_learned"]), 1)
            self.assertGreaterEqual(len(record["tags"]), 2)
            for step in record["timeline"]:
                self.assertIn("relative_time", step)
                self.assertIn("event", step)
                self.assertRegex(step["relative_time"], r"^[-+]?\d{2}[mh]")

    def test_no_eval_ids_or_copied_inc_files(self):
        for record in self.records:
            self.assertTrue(record["incident_id"].startswith("HIST-"))
            self.assertNotIn("INC-", record["incident_id"])
        eval_ids = {p.stem for p in EVAL_INCIDENTS.glob("INC-*.json")}
        hist_ids = set(self.by_id)
        self.assertTrue(eval_ids)
        self.assertFalse(hist_ids & eval_ids)
        # Titles must not be copied from the evaluation incidents.
        eval_titles = {
            json.loads(p.read_text(encoding="utf-8")).get("title")
            for p in EVAL_INCIDENTS.glob("INC-*.json")
        }
        hist_titles = {r["title"] for r in self.records}
        self.assertFalse(hist_titles & eval_titles - {None})

    def test_dates_before_evaluation_window(self):
        for record in self.records:
            when = datetime.fromisoformat(record["occurred_at"])
            self.assertLess(when, EVAL_CUTOFF, record["incident_id"])

    def test_root_cause_stays_out_of_symptoms_and_signals(self):
        for record in self.records:
            for field in NARRATIVE:
                text = json.dumps(record[field]) if field != "title" else record["title"]
                self.assertIsNone(
                    FORBIDDEN.search(text),
                    f"{record['incident_id']} leaked a label into {field}: {text[:200]}",
                )
            for field, value in record.items():
                if field == "root_cause":
                    continue
                text = json.dumps(value) if not isinstance(value, str) else value
                for label in LABELS:
                    self.assertNotIn(label, text, f"{record['incident_id']} {field}")

    def test_variation_not_a_template(self):
        titles = [r["title"] for r in self.records]
        self.assertEqual(len(titles), len(set(titles)))
        services = {r["service"] for r in self.records}
        self.assertGreaterEqual(len(services), 4)
        self.assertTrue(services <= KNOWN_SERVICES)
        severities = {r["severity"] for r in self.records}
        self.assertGreaterEqual(len(severities), 3)
        durations = {r["duration_minutes"] for r in self.records}
        self.assertGreaterEqual(len(durations), 8)
        symptom_sets = {tuple(r["symptoms"]) for r in self.records}
        self.assertEqual(len(symptom_sets), 30)

    def test_overlapping_symptom_language(self):
        """Latency + 5xx should appear under more than one root cause."""
        db = [r for r in self.records if r["root_cause"] == DB]
        mem = [r for r in self.records if r["root_cause"] == MEM]
        down = [r for r in self.records if r["root_cause"] == DOWN]
        latency_5xx = lambda rs: any("latenc" in " ".join(r["symptoms"]).lower()
                                     and "5xx" in " ".join(r["symptoms"]).lower()
                                     for r in rs)
        self.assertTrue(latency_5xx(db) and latency_5xx(down))
        mem_mentions_errors = any(
            "5xx" in " ".join(r["symptoms"]).lower()
            or "error" in " ".join(r["symptoms"]).lower()
            for r in mem
        )
        self.assertTrue(mem_mentions_errors)

    def test_not_under_data_raw(self):
        self.assertEqual(KNOWLEDGE, ROOT / "knowledge" / "incidents")
        self.assertFalse(str(KNOWLEDGE).replace("\\", "/").endswith("data/raw/incidents"))
        self.assertFalse((ROOT / "data" / "raw" / "incidents" / "HIST-001.json").exists())

    def test_generator_is_deterministic(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            left = generate(seed=7, output_dir=Path(a))
            right = generate(seed=7, output_dir=Path(b))
        self.assertEqual(left, right)
        self.assertEqual(left[0]["incident_id"], "HIST-001")


if __name__ == "__main__":
    unittest.main()
