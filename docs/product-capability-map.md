# Product capability map

This map describes what the repository can do today. It is the input for building the investigation UI feature by feature.

The only HTTP route is `POST /api/incidents/investigate` (`src/api/routes/incidents.py`). It accepts `{"incident_id": "INC-011"}` (`incident_id` must match `INC-` plus three digits) and returns an `RCAResult`, or an error object `{"error", "detail"}`.

A successful body is not available in this environment until two external dependencies work: a Chroma store at `data/vectorstore/` and a Gemini project that accepts the API key. The code path is present. The persistent index is missing, and Gemini currently returns `403 PERMISSION_DENIED`.

Ground truth (`scenario`, `true_root_cause`, `fault_start_time`, `expected_symptoms`, `resolution`, and the other fields on `IncidentGroundTruth`) is loaded only by `load_ground_truth` and `load_evaluation_record`. It must not be shown as the investigation result.

The current `frontend/` page is a demo. It renders fixture data unless `NEXT_PUBLIC_INVESTIGATION_SOURCE=live`. That page is not evidence that the API fields below are coming from Gemini.

Classes used below:

1. Directly usable by the frontend now (present on the existing HTTP response).
2. Available internally, not exposed as its own API data.
3. Partially implemented (code exists; the successful path is blocked or the response drops detail).
4. Test-only.
5. Not implemented.

---

## 1. Run an investigation

| | |
|---|---|
| Class | 1, with a class 3 runtime dependency |
| Source | `src/api/routes/incidents.py` `investigate_incident`; `src/investigation/investigator.py` `InvestigationService.investigate` |
| Input | JSON `incident_id` |
| Output | `RCAResult` |
| Frontend can consume it | Yes, as the response contract. A live 200 currently fails closed: missing Chroma is 503 `vector_store_missing`; a Gemini or retrieval failure is 502. |
| Endpoint | `POST /api/incidents/investigate` |
| Smallest change to expose | None for the contract. Building the index and restoring Gemini access is an operations step, not a new route. |
| Show in the UI | Yes. This is the primary action. |
| UI | One investigation view for the selected incident. Do not add a second workflow. |
| Depends on | Incident files, derived anomaly and correlation JSON, retrieval, Gemini, evidence validation. |

`InvestigationService.investigate` loads the incident file, calls `Retriever.retrieve_incident`, builds `InvestigationContext`, then `GeminiInvestigator.investigate`.

## 2. Investigation summary

| | |
|---|---|
| Class | 1 |
| Source | `src/investigation/models.py` `RCAResult.summary` |
| Input | Produced by the model from the investigation context |
| Output | One non-empty string |
| Frontend can consume it | Yes, on a 200 body |
| Endpoint | Same POST |
| Smallest change | None |
| Show in the UI | Yes |
| UI | A short summary above the hypothesis |
| Depends on | Run an investigation |

## 3. Root-cause hypothesis

| | |
|---|---|
| Class | 1 |
| Source | `RCAResult.root_cause` (`RootCauseHypothesis`) |
| Input | Same investigation |
| Output | `cause`, `confidence`, `supporting_evidence_ids`, `contradicting_evidence_ids`, `rationale` |
| Frontend can consume it | Yes |
| Endpoint | Same POST |
| Smallest change | None |
| Show in the UI | Yes. This is the focus of the page. |
| UI | The `cause` text, the rationale, and links to the cited ids. If `cause` is `INSUFFICIENT_EVIDENCE`, do not present a failure type. |
| Depends on | Run an investigation, evidence validation |

`confidence` on the hypothesis must match `RCAResult.confidence`. A stated cause other than `INSUFFICIENT_EVIDENCE` must cite at least one supporting id.

## 4. Confidence

| | |
|---|---|
| Class | 1 |
| Source | `RCAResult.confidence` and `RootCauseHypothesis.confidence` |
| Input | Model score |
| Output | Float in `[0, 1]` |
| Frontend can consume it | Yes |
| Endpoint | Same POST |
| Smallest change | None |
| Show in the UI | Yes, with the wording already in the schema: an uncalibrated ranking score, not a probability |
| UI | The number and that label. Do not say "probability". |
| Depends on | Root-cause hypothesis |

## 5. Alternative causes

| | |
|---|---|
| Class | 1 |
| Source | `RCAResult.alternative_causes` |
| Input | Same investigation |
| Output | A list of `RootCauseHypothesis`. The list may be empty. |
| Frontend can consume it | Yes |
| Endpoint | Same POST |
| Smallest change | None |
| Show in the UI | Yes |
| UI | Each cause, its rationale, and its evidence ids. The array order is the model's order. Do not invent a rank badge. The per-hypothesis `confidence` is the same uncalibrated score. |
| Depends on | Run an investigation |

## 6. Supporting evidence references

| | |
|---|---|
| Class | 1 for the reference, 3 for the operational detail |
| Source | `RCAResult.supporting_evidence` (`EvidenceReference`); rewritten by `validate_rca` in `src/investigation/evidence.py` |
| Input | Ids the model cited on hypotheses |
| Output | `evidence_id`, `source_type` (`LOG`, `METRIC_ANOMALY`, `ANOMALY_WINDOW`, `HISTORICAL_INCIDENT`, `TECHNICAL_DOCUMENT`), `short_description` |
| Frontend can consume it | Yes, those three fields |
| Endpoint | Same POST |
| Smallest change | None for the reference. Service, raw log text, metric value, and retrieval score are not on this object. |
| Show in the UI | Yes |
| UI | Cards for the returned references. Descriptions must be the returned `short_description`, which validation copies from the supplied evidence rather than from model-invented text. |
| Depends on | Evidence validation, evidence catalog |

`validate_rca` replaces the model's supporting-evidence list with the unique supporting ids from the primary hypothesis and the alternatives.

## 7. Contradicting evidence references

| | |
|---|---|
| Class | 1, with the same detail limit as supporting evidence |
| Source | `RCAResult.contradicting_evidence` |
| Input | Contradicting ids on the hypotheses |
| Output | Same `EvidenceReference` shape |
| Frontend can consume it | Yes |
| Endpoint | Same POST |
| Smallest change | None |
| Show in the UI | Yes, visually distinct from supporting evidence |
| UI | Cards or a second list. An id can appear as support for one hypothesis and as a contradiction for another. |
| Depends on | Evidence validation |

## 8. Cited timeline

| | |
|---|---|
| Class | 1 |
| Source | `RCAResult.timeline` (`TimelineEntry`) |
| Input | Timeline ids the model returned, then rewritten |
| Output | `evidence_id`, `timestamp`, `description` |
| Frontend can consume it | Yes |
| Endpoint | Same POST |
| Smallest change | None for this thin timeline. It has no `service`, event kind, or severity. Those live on the observational timeline (capability 18). |
| Show in the UI | Yes, labeled as cited observations. State that earlier does not mean causal. |
| UI | A list ordered as returned. Timestamp and description come from the supplied evidence after validation, not from text the model invented. |
| Depends on | Observational timeline, evidence validation |

## 9. Recommended actions

| | |
|---|---|
| Class | 1 |
| Source | `RCAResult.recommended_actions` (`RecommendedAction`) |
| Input | Model output, ids checked against the context |
| Output | `action`, `rationale`, `evidence_ids` |
| Frontend can consume it | Yes |
| Endpoint | Same POST |
| Smallest change | None |
| Show in the UI | Yes, as checks for a person. There is no executor. |
| UI | A numbered list of the returned actions and their evidence ids. No button that applies a change. |
| Depends on | Run an investigation, evidence validation |

For a stated cause, validation rejects an action that has no evidence ids. `INSUFFICIENT_EVIDENCE` may recommend collecting more evidence with an empty id list.

## 10. Similar incidents

| | |
|---|---|
| Class | 1 for the note, 2 for the historical record |
| Source | `RCAResult.similar_incidents` (`SimilarIncident`) |
| Input | Model output. `validate_rca` rejects an id that was not in the retrieval hits. |
| Output | `incident_id` (a `HIST-*` id) and `similarity_note` |
| Frontend can consume it | Yes, those two fields only |
| Endpoint | Same POST |
| Smallest change | To show symptoms, date, service, or score, add those fields from `HistoricalIncidentResult` or stop relying on the model to repeat them. Do not copy `historical_root_cause` into the current conclusion. |
| Show in the UI | Yes, as background. The note must not be presented as this incident's cause. |
| UI | One card per returned item. If the note is the only text, show only the note. |
| Depends on | Historical retrieval |

## 11. Insufficient evidence

| | |
|---|---|
| Class | 1 |
| Source | `INSUFFICIENT_EVIDENCE` in `src/investigation/models.py`; `insufficient_result` in `src/investigation/evidence.py`; the prompt rule in `src/investigation/prompt.py` |
| Input | Empty investigation evidence skips Gemini and returns this result. Otherwise the model may choose this cause. |
| Output | `root_cause.cause == "INSUFFICIENT_EVIDENCE"`, confidence `0` when built by `insufficient_result`, empty supporting ids allowed |
| Frontend can consume it | Yes |
| Endpoint | Same POST |
| Smallest change | None |
| Show in the UI | Yes |
| UI | A distinct state. Do not map it onto database, memory, or downstream timeout. |
| Depends on | Run an investigation |

## 12. API error states

| | |
|---|---|
| Class | 1 |
| Source | `src/api/main.py` `_STATUS`; `src/api/schemas.py` `InvestigateRequest`; `src/investigation/models.py` error types |
| Input | Bad JSON, unknown id, missing configuration, missing Chroma, retrieval failure, Gemini failure, invalid RCA |
| Output | `{"error", "detail"}` |
| Frontend can consume it | Yes |
| Endpoint | Same POST |
| Smallest change | None. There is no health route. |
| Show in the UI | Yes |
| UI | 422: the id is malformed. 404 `not_found`: no such incident. 503 `configuration_error` or `vector_store_missing`: the service is not ready. 502 `retrieval_failed`, `investigation_failed`, or `invalid_rca`: the run failed. Do not show stack traces or key material. `detail` is already passed through a redaction helper on Gemini and retrieval failures. |
| Depends on | Run an investigation |

FastAPI itself returns 422 for a body that fails `InvestigateRequest`. That body is FastAPI's validation error, not `{"error", "detail"}`.

## 13. Incident catalog

| | |
|---|---|
| Class | 2 |
| Source | `src/ingestion/incident_loader.py` `list_incident_ids`; files `data/raw/incidents/INC-*.json`; index `data/generated/incidents_index.csv` |
| Input | `data/` directory |
| Output | Sorted incident ids. The CSV also has evaluation columns; do not send those to the UI. |
| Frontend can consume it | No |
| Endpoint | None |
| Smallest change | `GET /api/incidents` returning id, title, service, severity, and start time from `IncidentContext` only |
| Show in the UI | Yes, as the way to choose an incident. The page can start from a known id, but a list is the real catalog. |
| UI | A single selector of incident ids and alert titles. No scenario label. |
| Depends on | Incident context |

There are 35 `INC-*` cases on disk.

## 14. Incident context

| | |
|---|---|
| Class | 2 |
| Source | `load_incident_context`; model `IncidentContext` in `src/ingestion/models.py` |
| Input | `data/raw/incidents/INC-XXX.json`, context fields only |
| Output | `incident_id`, `title`, `service`, `severity`, `start_time`, `end_time`, `duration_minutes`, `window_start`, `window_end`, `description` |
| Frontend can consume it | No. The RCA response does not include this header. |
| Endpoint | None. The investigation prompt contains some of these fields, but they are not returned. |
| Smallest change | Include the context object on the investigate response, or add `GET /api/incidents/{incident_id}`. |
| Show in the UI | Yes |
| UI | Header: id, title, severity, alerting service, start, end, duration, description. `service` is where the alert fired, not a proven root-cause service. |
| Depends on | Incident files |

## 15. Ground truth

| | |
|---|---|
| Class | 2 |
| Source | `load_ground_truth`, `load_evaluation_record`, `IncidentGroundTruth` |
| Input | The same incident JSON, ground-truth fields only |
| Output | Scenario, true cause, variant, fault time, expected symptoms, affected services, resolution |
| Frontend can consume it | No, and it must stay that way for the investigation view |
| Endpoint | None |
| Smallest change | Do not add an investigation endpoint for these fields |
| Show in the UI | No |
| UI | None on the investigation page |
| Depends on | Nothing the investigator should see |

## 16. Logs

| | |
|---|---|
| Class | 2 |
| Source | `src/ingestion/log_parser.py` `load_logs`; `data/raw/logs/INC-XXX.jsonl` |
| Input | JSON Lines path |
| Output | `LogEvent`: timestamp, service, host, level, logger, message, trace_id, incident_id, derived `event_type` |
| Frontend can consume it | No. Only logs selected into the correlation timeline can later be cited. The full file is not returned. |
| Endpoint | None |
| Smallest change | Do not dump every log line into the first UI. If a cited `LOG-*` id needs a drawer, add a lookup of that evidence item from the derived timeline. |
| Show in the UI | Only the cited or timeline-selected lines, not the full file |
| UI | A detail drawer on an evidence id |
| Depends on | Evidence catalog |

`event_type` is a description of the line, not a scenario label.

## 17. Metrics

| | |
|---|---|
| Class | 2 |
| Source | `src/ingestion/metric_loader.py` `load_metrics`; `data/raw/metrics/INC-XXX.csv` |
| Input | Metric CSV |
| Output | `MetricPoint` rows: `cpu_usage`, `memory_usage`, `request_rate`, `latency_ms`, `error_rate`, `db_connection_utilization`, `downstream_latency_ms`. Blank cells are `None`. |
| Frontend can consume it | No |
| Endpoint | None |
| Smallest change | `GET /api/incidents/{incident_id}/metrics` for the alerting service and the series that anomaly windows name. Returning every service and minute will be large. |
| Show in the UI | Yes, for the series that the anomaly report marks, with the baseline the detector used |
| UI | A few series, not seven charts for every service |
| Depends on | Anomaly points |

## 18. Anomaly points

| | |
|---|---|
| Class | 2 |
| Source | `src/detection/detector.py` `detect_incident` / `detect_anomalies`; files `data/derived/anomalies/INC-XXX.json` |
| Input | `IncidentEvidenceBundle` metrics. No ground truth. |
| Output | `IncidentAnomalyReport`: `points` (`AnomalyPoint`) and `windows` |
| Frontend can consume it | No |
| Endpoint | None. `scripts/detect_anomalies.py` writes the JSON. |
| Smallest change | `GET /api/incidents/{incident_id}/anomalies` returning the existing derived file, or recomputing with `detect_incident` |
| Show in the UI | Yes |
| UI | Points or a summary per series: service, metric, value, baseline mean, z-score, severity, direction. Severity is the detector's label, not the alert severity. |
| Depends on | Metrics |

The detector uses a causal rolling baseline (`src/detection/baseline.py`) and z-score rules (`src/detection/statistical.py`). Defaults are documented as MVP heuristics in `docs/anomaly_detection.md`.

## 19. Anomaly windows

| | |
|---|---|
| Class | 2 |
| Source | `src/detection/windowing.py` `build_anomaly_windows`; stored on `IncidentAnomalyReport.windows` |
| Input | Anomaly points, default gap of 2 minutes |
| Output | `AnomalyWindow`: start, end, duration, severity, count, services, metrics, peak z-score, peak metric, peak service, peak time |
| Frontend can consume it | No. A cited `ANOMWIN-*` reference does not include this structure. |
| Endpoint | None |
| Smallest change | Include windows on the anomalies response |
| Show in the UI | Yes |
| UI | Bands on the metric charts and rows in the timeline. A window is a cluster of odd points, not a cause. |
| Depends on | Anomaly points |

## 20. Observational timeline

| | |
|---|---|
| Class | 2 |
| Source | `src/correlation/timeline.py` `correlate_incident`; files `data/derived/correlation/INC-XXX.json` |
| Input | Evidence bundle plus `IncidentAnomalyReport` |
| Output | `IncidentTimeline`: events, evidence items, involved services, first observed event, earliest relevant log, earliest anomaly, anomaly windows, investigation span |
| Frontend can consume it | No. This is richer than `RCAResult.timeline`. |
| Endpoint | None. `scripts/correlate_incidents.py` writes the JSON. |
| Smallest change | `GET /api/incidents/{incident_id}/timeline` returning the derived timeline |
| Show in the UI | Yes. Prefer this over the thin cited timeline when both exist. |
| UI | Time-ordered events with service, source type, evidence id, and severity when present. Caption: order is not causation. `src/correlation/temporal.py` only records overlap and proximity. |
| Depends on | Logs, anomaly windows, incident context |

## 21. Evidence catalog

| | |
|---|---|
| Class | 2 |
| Source | `src/correlation/evidence.py` `EvidenceIdFactory` and selectors; `EvidenceItem` in `src/correlation/models.py`; historical and technical ids added in `src/investigation/context_builder.py` |
| Input | Selected logs, anomaly points, anomaly windows, retrieval hits |
| Output | Ids. Logs and anomalies use `LOG-`, `ANOM-`, and `ANOMWIN-` plus six digits. Historical ids are `HIST-*`. Technical ids look like `database_003`. |
| Frontend can consume it | Only the ids that happen to be cited on the RCA result |
| Endpoint | None for the full catalog |
| Smallest change | Return `evidence_items` from the timeline response, plus the retrieval hits used for that run |
| Show in the UI | Yes |
| UI | The catalog is what a cited id opens. Each item has id, source, time, service, and summary. |
| Depends on | Observational timeline, historical retrieval, technical retrieval |

High-volume logs are collapsed. Not every raw log receives an id.

## 22. Retrieval query

| | |
|---|---|
| Class | 2 |
| Source | `src/retrieval/query_builder.py` `build_query_for_incident` / `build_retrieval_query` |
| Input | Incident context, anomaly report, observational timeline. Evaluation fields are rejected if they appear. |
| Output | One observational query string |
| Frontend can consume it | No |
| Endpoint | None. It is stored on `InvestigationContext.retrieval_query` and placed in the prompt. It is not on `RCAResult`. |
| Smallest change | Optional text on a retrieval response. It is not required for the first UI. |
| Show in the UI | Only as a short "what was searched" note, if shown at all |
| UI | Muted text under similar incidents |
| Depends on | Incident context, anomaly report, observational timeline |

## 23. Historical incident retrieval

| | |
|---|---|
| Class | 2 for the hit, 1 for the note the model chooses to return |
| Source | `src/retrieval/historical.py` `retrieve_similar_incidents`; `src/retrieval/retriever.py` `Retriever.retrieve`; collection `historical_incidents` |
| Input | Query text, `top_k` default 3 |
| Output | `HistoricalIncidentResult`: rank, `incident_id`, score, observational text, metadata (`service`, `date`, `severity`, `duration_minutes`, and `historical_root_cause` in metadata only) |
| Frontend can consume it | No, unless the model copies a similarity note into `similar_incidents` |
| Endpoint | None. The investigate call runs retrieval and does not return the hits. |
| Smallest change | Return the retrieval hits beside the RCA result, with `historical_root_cause` omitted from the current-incident conclusion |
| Show in the UI | Yes, as background |
| UI | `HIST-*` id, score, service, date, and the observational text. State that a past cause is not this incident's cause. |
| Depends on | Retrieval query, vector index |

Indexed text is built by `render_historical_text`, which omits the structured root-cause label. The label remains in Chroma metadata. Knowledge files are `knowledge/incidents/HIST-001.json` through `HIST-030.json`.

## 24. Technical-document retrieval

| | |
|---|---|
| Class | 2 for the chunk, 3 if the model cites it |
| Source | `src/retrieval/technical.py` `retrieve_technical_documents` and `chunk_markdown`; collection `technical_documents` |
| Input | Same query, `top_k` default 3 |
| Output | `TechnicalDocumentResult`: rank, `document_id`, section, score, text, metadata (`document_name`, `section`) |
| Frontend can consume it | Only when a cited `EvidenceReference` has `source_type` `TECHNICAL_DOCUMENT`. The response then has a short description, not the section path or full excerpt. |
| Endpoint | None for the hits |
| Smallest change | Return the technical hits next to the RCA result |
| Show in the UI | Yes |
| UI | Title, section, excerpt, chunk id, source file name from metadata |
| Depends on | Retrieval query, vector index |

Source documents are `knowledge/docs/database.md`, `memory.md`, `networking.md`, and `troubleshooting.md`. Chunking splits on `##` headings, merges sections under 280 characters, and splits sections over 1800 characters.

## 25. Vector index

| | |
|---|---|
| Class | 3 |
| Source | `src/retrieval/indexer.py` `build_index`; `scripts/build_vector_index.py` |
| Input | Historical JSON, technical markdown, Gemini embeddings (`GeminiEmbeddingProvider`, default `gemini-embedding-001`) |
| Output | Persistent Chroma at `data/vectorstore/` with collections `historical_incidents` and `technical_documents` |
| Frontend can consume it | No |
| Endpoint | None |
| Smallest change | Run the existing script once Gemini embeddings are allowed. Do not add a fake index. |
| Show in the UI | No |
| UI | None. A missing store is already the 503 `vector_store_missing` error. |
| Depends on | Gemini embeddings |

`HashEmbeddingProvider` is test-only (capability 32). `open_store` uses `chromadb.PersistentClient`. Retrieval space for the real collections is cosine.

## 26. Investigation context and prompt

| | |
|---|---|
| Class | 2 |
| Source | `src/investigation/context_builder.py` `build_investigation_context`; `src/investigation/prompt.py` `render_prompt` |
| Input | Incident context, derived anomaly JSON, derived correlation JSON, `RetrievalResult` |
| Output | `InvestigationContext` (header fields plus `CitedEvidence` list) and a prompt string |
| Frontend can consume it | No |
| Endpoint | None |
| Smallest change | Do not return the raw prompt |
| Show in the UI | No |
| UI | None |
| Depends on | Context, anomalies, timeline, retrieval |

The prompt forbids treating the first anomaly, a deployment, severity, or duration as proof, and it forbids copying a historical outcome onto the current incident.

## 27. Evidence validation

| | |
|---|---|
| Class | 2 |
| Source | `src/investigation/evidence.py` `validate_rca` |
| Input | Draft `RCAResult` and `InvestigationContext.allowed_ids()` |
| Output | A rewritten `RCAResult`, or `InvalidRCA` |
| Frontend can consume it | Only the outcome: a 200 body whose ids are known, or 502 `invalid_rca` |
| Endpoint | Enforced inside the POST. No separate route. |
| Smallest change | None |
| Show in the UI | The 502 state, not the validator internals |
| UI | "The investigation result cited evidence that was not supplied." |
| Depends on | Evidence catalog, RCA generation |

Unknown ids are rejected. They are not filled in. Descriptions and timestamps on references are replaced from the supplied evidence.

## 28. Embeddings

| | |
|---|---|
| Class | 3 |
| Source | `src/retrieval/embeddings.py` `GeminiEmbeddingProvider` |
| Input | Text, task `document` or `query` |
| Output | Normalized vectors. Default model `gemini-embedding-001`, default size 768, `task_type` set for that model. |
| Frontend can consume it | No. The browser must not call Gemini. |
| Endpoint | None |
| Smallest change | None in the UI |
| Show in the UI | No |
| UI | None |
| Depends on | `GEMINI_API_KEY` |

Query embeddings use `RETRIEVAL_QUERY`. Document embeddings use `RETRIEVAL_DOCUMENT`. Ranking in `src/retrieval/scoring.py` converts Chroma cosine distance to `1 - distance`.

## 29. Gemini RCA call

| | |
|---|---|
| Class | 3 |
| Source | `src/investigation/investigator.py` `GeminiInvestigator` |
| Input | The rendered prompt |
| Output | JSON constrained to `RCAResult` (`response_schema`), temperature 0, model from `GENAI_MODEL` or `gemini-2.5-flash`, up to `GENAI_MAX_ATTEMPTS` (default 2) |
| Frontend can consume it | Only through the POST, and only after the call succeeds |
| Endpoint | Inside the POST |
| Smallest change | Restore API access. Do not mock a successful RCA in the API. |
| Show in the UI | The result and the 502 failure. Do not animate fake pipeline stages as if they ran. |
| UI | The investigation result, or the error state |
| Depends on | Prompt, vector index, evidence validation |

`gemini-2.5-flash` is the code default. A diagnostic call against the configured key returned 404 for that model and 403 for a newer generation model and for embeddings. That is an external block, not a missing function.

## 30. Frontend investigation page

| | |
|---|---|
| Class | 3 |
| Source | `frontend/app/investigation/[incidentId]/page.tsx`, `frontend/lib/api/investigation.ts`, `frontend/data/investigation-fixture.ts` |
| Input | Route id, optional `preview` query |
| Output | A demo layout. Default data is the fixture, not FastAPI. |
| Frontend can consume it | The fixture is local. Live mode posts to FastAPI and is not the default. |
| Endpoint | Client calls `POST /api/incidents/investigate` only when `NEXT_PUBLIC_INVESTIGATION_SOURCE=live` |
| Smallest change | Point the page at the real response fields in this map. Do not keep illustrating metrics that the API does not return. |
| Show in the UI | The page is the product surface. Fixture-only charts are not a backend capability. |
| UI | Rebuild from this map |
| Depends on | The capabilities above |

Header severity, metric series, "why it matters" copy, and historical resolution text in the current fixture are not fields of `RCAResult`.

## 31. Dataset generation and validation

| | |
|---|---|
| Class | 4 for product purposes (benchmark tooling) |
| Source | `scripts/generate_logs.py`, `scripts/validate_dataset.py`, `scripts/generate_knowledge.py` |
| Input | Seed and counts |
| Output | `data/raw/`, `data/generated/`, `knowledge/` |
| Frontend can consume it | No |
| Endpoint | None |
| Smallest change | Do not expose |
| Show in the UI | No |
| UI | None |
| Depends on | Nothing in the request path |

## 32. Hash embeddings

| | |
|---|---|
| Class | 4 |
| Source | `src/retrieval/embeddings.py` `HashEmbeddingProvider`; `tests/test_retrieval.py` |
| Input | Text |
| Output | Deterministic vectors for tests |
| Frontend can consume it | No |
| Endpoint | None |
| Smallest change | Do not use it for the product index |
| Show in the UI | No |
| UI | None |
| Depends on | None |

## 33. Mocked investigation in API tests

| | |
|---|---|
| Class | 4 |
| Source | `tests/test_api.py`, `tests/test_investigation.py` |
| Input | A fake investigator |
| Output | Status codes and schema checks without Gemini |
| Frontend can consume it | No |
| Endpoint | The tests call the same route with an injected service |
| Smallest change | None |
| Show in the UI | No |
| UI | None |
| Depends on | None |

## 34. Pipeline progress events

| | |
|---|---|
| Class | 5 |
| Source | None. The investigate call is one synchronous function. |
| Input | — |
| Output | — |
| Frontend can consume it | No |
| Endpoint | None |
| Smallest change | Do not invent staged progress. A single pending state is honest. |
| Show in the UI | A waiting state only, without checkmarks for steps the client cannot observe |
| UI | "Running investigation" until the POST returns |
| Depends on | — |

## 35. Accuracy evaluation

| | |
|---|---|
| Class | 5 |
| Source | Ground-truth loaders exist. No Top-1 or Top-3 scorer is implemented. |
| Input | — |
| Output | — |
| Frontend can consume it | No |
| Endpoint | None |
| Smallest change | Out of scope for the investigation UI |
| Show in the UI | No |
| UI | None |
| Depends on | Ground truth, which stays off this page |

## 36. Health check

| | |
|---|---|
| Class | 5 |
| Source | None. `src/api/main.py` registers one router. |
| Input | — |
| Output | — |
| Frontend can consume it | No. Readiness is visible only by calling investigate (503 if the key or Chroma store is missing). |
| Endpoint | None |
| Smallest change | Not required to render an investigation |
| Show in the UI | No |
| UI | Use the investigate error states |
| Depends on | — |

## 37. Authentication

| | |
|---|---|
| Class | 5 |
| Source | None |
| Input | — |
| Output | — |
| Frontend can consume it | No |
| Endpoint | None |
| Smallest change | Do not add it for this UI |
| Show in the UI | No |
| UI | None |
| Depends on | — |

## 38. Remediation execution

| | |
|---|---|
| Class | 5 |
| Source | Recommended actions are text. Nothing applies them. |
| Input | — |
| Output | — |
| Frontend can consume it | No |
| Endpoint | None |
| Smallest change | Do not add an execute action |
| Show in the UI | Show the text only |
| UI | No run, rollback, or deploy control |
| Depends on | Recommended actions |
