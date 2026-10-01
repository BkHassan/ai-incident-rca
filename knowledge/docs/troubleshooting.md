# Incident investigation workflow

An investigation starts from the alert and the evidence around it. The goal of the first pass is a timeline of what was observed, which series moved, and which did not. Naming a cause comes after that record exists. This note is a general procedure for services that expose logs, a short metric set, and deploy events.

## Logs and metrics

Metrics show shape over time: latency, error rate, request rate, CPU, memory, database connection utilization, and downstream latency. They are comparable across minutes and are the right tool for "did this series leave its recent baseline?". Logs name the operation that failed: a timeout, a connection wait, a GC pause, a health check, a retry. A metric spike without a matching log is still real. A single error log without a metric movement may be noise.

Prefer counts of a log event over one dramatic line. A handful of slow-query warnings during a quiet hour is different from a sustained run of acquire timeouts. Collapse repeated lines and keep the first and last timestamp. High-volume request logs are context. WARN and ERROR lines, timeouts, and lifecycle events are the ones to put on the first timeline.

## Time order

Place logs and metric changes on one clock. Note what began first: a latency climb, a connection-wait line, an error-rate page, a memory slope. Order is not the same as cause. A deploy can precede an incident and be unrelated. A caller timeout can precede the dependency's own alert because the caller has the shorter deadline.

Use the alert start as the reference, and look back far enough for deploys, config reloads, and restarts. Memory slopes in particular start long before the page. Connection-pool waits often start a few minutes before the error rate crosses the page threshold. Downstream latency often moves before the caller's 5xx rate.

## Changes

Record deploys, config reloads, feature flags, autoscaling, and restarts as events, with the service name and the version or flag when the log has it. A change on a caller and a change on a dependency are different facts. "No local deploy" is also a fact: it narrows attention toward traffic, a dependency, or a slow leak that did not need a release in this window.

Do not treat the nearest deploy as the cause by default. Check whether the metric that moved is one that deploy could affect, and whether the same metric moved on instances that did not receive it.

## A practical first pass

1. Identify the alerting service, the severity, and the window the page covers.
2. List metric series that left baseline, and series that stayed put. A negative finding (memory flat, or connection utilization flat) is evidence.
3. List log event types in that window: timeouts, connection waits, GC or allocation messages, retries, health-check failures, deploys.
4. Note other services that appear in those logs. Callers often page first. The dependency or the database may be where the series actually moved.
5. Only then compare the pattern with previous incidents and with runbooks. Similar latency and 5xx text appears in more than one failure mode. The series that moved, and the series that did not, are what separate them.

## When the signal is weak

Some alerts fire while metrics stay inside the usual band and the timeline has no timeout, allocation, or connection-wait cluster. That is an observation, not a prompt to force a failure mode. Say which series were checked and that they did not depart. Keep the page in the record. A later look can add a deploy or a dependency that was outside the first window. Inventing a mechanism to match the page title produces a confident and unsupported account.

Dashboards and runbooks should make the negative checks easy: utilization beside latency, memory slope beside error rate, downstream latency beside caller CPU. The investigation note should be specific enough that another engineer can retrieve the same logs and series and see the same order.
