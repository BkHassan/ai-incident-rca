# Historical incident knowledge base

This directory holds **prior** incidents for later similarity retrieval. It is not the evaluation dataset.

| Location | Role |
|---|---|
| `data/raw/` (`INC-001` … `INC-035`) | Current investigation cases (metrics, logs, ground truth) |
| `knowledge/incidents/` (`HIST-001` … `HIST-030`) | Closed postmortems from an earlier period |

Do not copy files between the two. Historical IDs use the `HIST-` namespace. Dates are all before 2026-01-08, which is when the evaluation window starts.

## Schema

Each `HIST-NNN.json` is a short postmortem: symptoms, observed signals, a relative timeline, contributing factors, resolution, lessons, and tags. The structured root-cause label lives only in `root_cause`. Symptom and signal text stays observational (latency, waits, 5xx, memory growth, dependency timeouts) so a later retriever cannot cheat by matching the enum string.

Thirty records, ten of each:

- `DB_CONNECTION_POOL_EXHAUSTION`
- `MEMORY_LEAK`
- `DOWNSTREAM_SERVICE_TIMEOUT`

Services match the rest of the project (`api-gateway`, `orders-api`, `payment-api`, `inventory-service`, `recommendation-service`, `database`) plus the same external names (`acquirer-gateway`, `warehouse-api`).

Some cases are deliberately overlapping: high latency plus 5xx appear under more than one root cause; a few database incidents mention caller-side timeouts; a few downstream incidents mention connections held while waiting.

## Regenerating

```bash
python scripts/generate_knowledge.py          # seed 7
python -m unittest tests.test_knowledge
```

`knowledge/docs/` holds general troubleshooting notes (database connections, memory growth, downstream latency, and an investigation workflow). Indexing those notes, and these postmortems, is a separate retrieval step. It does not rank a current incident's root cause.
