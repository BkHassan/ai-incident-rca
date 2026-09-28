# MVP Architecture

## Architecture Goal

Build a focused incident-investigation system rather than a complete AIOps platform.

The system should solve one problem well:

> **AI-assisted root-cause analysis of software incidents.**

## High-Level Flow

```text
                     INCIDENT
                         |
                         v
                  DATA INGESTION
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
        LOGS          METRICS         CONTEXT
          |              |              |
          +--------------+--------------+
                         |
                         v
                STRUCTURED EVIDENCE
                         |
                         v
             ANOMALY / EVENT EXTRACTION
                         |
                         v
              TEMPORAL + CONTEXTUAL
                   CORRELATION
                         |
                         v
                 CANDIDATE CAUSES
                         |
              +----------+----------+
              |                     |
              v                     v
     HISTORICAL INCIDENTS     TECHNICAL DOCUMENTS
              |                     |
              +----------+----------+
                         |
                         v
                   AI REASONING
                         |
                         v
                EVIDENCE VERIFICATION
                         |
                         v
                 ROOT-CAUSE RANKING
                         |
                         v
                  STRUCTURED RCA
                         |
                         v
                    WEB UI
```

## Component Responsibilities

### 1. Data Ingestion

Loads the incident, logs, metrics, historical incidents, and documentation for the investigation.

### 2. Parsing / Normalization

Converts raw log and metric records into predictable structured representations.

### 3. Evidence Extraction

Finds relevant abnormal metrics, error events, and incident-related log records rather than passing all raw data to the LLM.

### 4. Temporal and Contextual Correlation

Builds a timeline and identifies relationships between events around the incident window.

Example:

```text
10:40 deployment
10:42 database errors increase
10:43 latency increases
10:44 5xx errors increase
```

### 5. Candidate-Cause Generation

Produces a small set of plausible root-cause hypotheses from the structured evidence.

### 6. Historical Incident Retrieval

Retrieves similar historical incidents from the knowledge base.

### 7. Technical Evidence Retrieval

Retrieves relevant troubleshooting or technical-documentation passages.

### 8. AI Reasoning

Uses the structured evidence, historical incidents, and technical documentation to evaluate and rank hypotheses.

The model must work from supplied evidence rather than inventing unsupported facts.

### 9. Evidence Verification

Checks that important claims in the RCA are linked to actual evidence records or document sources.

### 10. Root-Cause Ranking

Returns the ranked hypotheses with confidence/score and evidence references.

### 11. RCA Report

Produces a structured machine-readable result containing:

- incident summary
- root-cause ranking
- confidence/score
- supporting evidence
- contradicting evidence
- timeline
- similar incidents
- technical sources
- recommended actions

## Initial Technology Choices

### Backend / AI

- Python
- FastAPI
- Pydantic
- Pandas
- NumPy
- scikit-learn
- ChromaDB
- Google GenAI SDK

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- Recharts

### Data

- JSON
- CSV
- ChromaDB

### Development / Packaging

- Git
- GitHub
- Docker
- Docker Compose
- environment variables via `.env`

## Initial Data Strategy

The MVP uses controlled synthetic data so that every test case has a known ground-truth root cause.

Three failure scenarios are supported initially:

1. DB connection pool exhaustion
2. Memory leak
3. Downstream timeout

The benchmark target is:

- 10 incidents per scenario = 30 incident cases
- 5 normal/no-failure cases
- 35 total evaluation cases

## Engineering Principle

The system is intentionally divided into two broad layers:

### Deterministic Investigation Layer

- parsing
- normalization
- anomaly detection
- event extraction
- temporal correlation
- evidence selection

### AI Reasoning Layer

- hypothesis generation
- historical/document retrieval interpretation
- evidence-based hypothesis ranking
- structured RCA generation

This separation prevents the project from becoming a simple `logs -> LLM -> answer` application.

## MVP Boundaries

Do not add Kafka, Kubernetes, OpenTelemetry, autonomous remediation, multi-agent orchestration, or production-scale infrastructure before the core investigation loop works end-to-end.

The first vertical slice should be:

```text
one synthetic incident
-> evidence extraction
-> timeline
-> similar incident retrieval
-> technical evidence retrieval
-> RCA JSON
-> displayed in UI
```

## Evaluation

The project will report actual measured results for:

- Top-1 root-cause accuracy
- Top-3 root-cause recall
- evidence relevance / grounding quality
- end-to-end RCA latency

Target values should not be invented in advance. The README will contain the measured results obtained from the implemented benchmark.
