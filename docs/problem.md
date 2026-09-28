# Problem Definition

## Business Problem

When software incidents occur, engineers often spend significant time manually inspecting application logs, operational metrics, incident descriptions, previous incidents, and technical documentation to determine what caused the failure. The information needed for diagnosis is distributed across multiple sources, making investigation repetitive and time-consuming.

## Target User

The primary user is a:

- software engineer,
- SRE / site reliability engineer, or
- operations / application support engineer

responsible for investigating application incidents.

## Core Job-to-be-Done

> Given a software incident and the available operational evidence, help the engineer identify the most probable root cause and understand why the system reached that conclusion.

## MVP Question

For a known incident, can the system combine multiple evidence sources and rank the correct root cause among a small set of plausible hypotheses?

## Inputs

### 1. Incident Context

- incident ID
- incident title/summary
- severity
- affected service
- start/end time or investigation window

### 2. Application Logs

Structured log records containing:

- timestamp
- service
- level
- message
- event/error type

### 3. Metrics

Timestamped measurements such as:

- request latency
- error rate
- CPU usage
- memory usage
- database connection utilization
- downstream request latency / timeout count

### 4. Historical Incidents

Previous incidents containing:

- symptoms
- affected service
- root cause
- resolution

### 5. Technical Documentation

Relevant technical material such as:

- troubleshooting guides
- runbooks
- configuration guidance
- service/database documentation

## Output

The system should return:

1. a ranked list of probable root causes;
2. a confidence/score for each hypothesis;
3. supporting evidence with source identifiers;
4. contradicting evidence when available;
5. a reconstructed incident timeline;
6. similar historical incidents;
7. relevant technical documentation;
8. recommended investigation/remediation steps;
9. a structured RCA report.

## Failure Scenarios

### SCENARIO_01 — DB_CONNECTION_POOL_EXHAUSTION

Expected observable pattern:

- database connection utilization becomes saturated;
- connection acquisition/timeout errors increase;
- application latency increases;
- API/server errors increase.

Ground truth root cause:

`DB_CONNECTION_POOL_EXHAUSTION`

### SCENARIO_02 — MEMORY_LEAK

Expected observable pattern:

- memory usage increases progressively;
- garbage-collection or memory-pressure signals increase;
- latency may increase;
- application errors/restarts may occur.

Ground truth root cause:

`MEMORY_LEAK`

### SCENARIO_03 — DOWNSTREAM_TIMEOUT

Expected observable pattern:

- downstream response latency increases;
- timeout count increases;
- dependent application endpoints become slower;
- propagated errors increase.

Ground truth root cause:

`DOWNSTREAM_TIMEOUT`

## Out of Scope

The MVP does not include:

- production infrastructure monitoring;
- autonomous production remediation;
- automatic deployment rollback;
- support for arbitrary incident classes;
- large-scale stream processing;
- a full enterprise observability platform.

## Definition of Done for the Problem

The problem definition is complete when the team can answer these questions without ambiguity:

- Who uses the system? → Software/SRE/operations engineer.
- What problem is solved? → Faster evidence-based incident RCA.
- What enters the system? → Incident + logs + metrics + history + docs.
- What leaves the system? → Ranked causes + evidence + RCA report.
- Which incidents are supported? → Three defined scenarios.
- How is success measured? → RCA accuracy, evidence quality, and latency.
