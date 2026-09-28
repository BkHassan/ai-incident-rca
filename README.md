# AI-Assisted Root-Cause Analysis for Software Incidents

## MVP

An AI-assisted system that helps software/SRE/operations engineers investigate application incidents by combining structured incident context, application logs, metrics, historical incidents, and technical documentation to identify and rank probable root causes with supporting evidence and generate a structured RCA report.

## Problem

When software incidents occur, engineers often need to manually inspect logs, metrics, incident context, previous incidents, and technical documentation to identify the root cause. This investigation can be slow, repetitive, and difficult to scale.

## User

Primary user:
- Software engineer
- SRE / Site Reliability Engineer
- Operations / application support engineer

## MVP Input

The MVP accepts:

1. **Incident context**
   - incident ID
   - title/summary
   - severity
   - affected service
   - incident time window

2. **Application logs**
   - timestamp
   - service
   - log level
   - message
   - event/error information

3. **Metrics**
   - timestamped operational measurements such as latency, error rate, memory usage, CPU usage, and database connection utilization

4. **Historical incidents**
   - previous incidents
   - symptoms
   - confirmed root cause
   - resolution information

5. **Technical documentation**
   - troubleshooting guides
   - runbooks
   - technical documentation

## MVP Output

For each incident, the system produces:

- ranked probable root causes
- confidence/score for each hypothesis
- supporting evidence
- contradicting evidence when available
- relevant timeline/events
- similar historical incidents
- relevant technical documentation
- recommended investigation/remediation steps
- structured RCA report

## MVP Scenarios

### SCENARIO_01 — DB_CONNECTION_POOL_EXHAUSTION

An application experiences database connection acquisition failures. Database connection utilization becomes saturated, application latency increases, and API errors increase.

### SCENARIO_02 — MEMORY_LEAK

An application service shows progressively increasing memory usage, followed by latency degradation, garbage-collection pressure, and eventually application errors or restart behavior.

### SCENARIO_03 — DOWNSTREAM_TIMEOUT

An application depends on a downstream service whose response time increases significantly. Timeout errors propagate to the application and eventually increase user-facing failures.

## MVP Scope Boundaries

The MVP does **not** attempt to:

- monitor real production infrastructure
- ingest millions of events per second
- automatically restart or modify production services
- perform autonomous remediation
- support every possible incident type
- build a complete enterprise observability platform
- guarantee a correct root cause

The MVP is a controlled diagnostic prototype using realistic synthetic incident data and a small knowledge base.

## Core Success Criteria

The MVP is considered successful when it can:

1. ingest a defined incident and its evidence;
2. detect/reconstruct relevant abnormal behavior and event relationships;
3. retrieve relevant historical incidents and technical evidence;
4. generate and rank root-cause hypotheses;
5. attach evidence to the hypotheses;
6. produce a structured RCA report;
7. evaluate the diagnosis against known ground truth.

## Initial Evaluation

The first benchmark will contain:

- 10 incidents for SCENARIO_01
- 10 incidents for SCENARIO_02
- 10 incidents for SCENARIO_03
- 5 normal/no-failure cases

Total: **35 test cases**.

Primary metrics:

- Top-1 root-cause accuracy
- Top-3 root-cause recall
- evidence relevance / grounding quality
- end-to-end RCA generation latency

## Project Status

Day 1 — Scope frozen.
