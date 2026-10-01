# Process memory, garbage collection, and growth

Process memory is the resident set of one service instance. It normally moves with traffic and cache size, then levels off. A climb that continues for tens of minutes or hours, while request rate is flat, is a different pattern from a brief spike during a deploy or a GC cycle.

## How memory grows

Allocations follow requests: parsing payloads, building responses, filling caches, and holding sessions. A stable service returns most of that memory to the allocator or the runtime. RSS then oscillates inside a band. A cache with a TTL or a maximum size stops growing once it is warm.

Unstable growth has a near-linear slope on `memory_usage` or RSS. The slope can be slow enough that a 15-minute rolling baseline barely flags the first part of the climb. Compare the level with the same hour on previous days, not only with the last few minutes. A container memory limit close to the healthy working set leaves little room before the runtime or the cgroup intervenes.

## Garbage collection and pauses

Managed runtimes (JVM, Go, Node, CPython) collect garbage on a schedule or when allocation fails. Short collections are normal. Longer pauses show up as latency spikes that line up with GC logs, heap-used warnings, or "GC overhead" messages. CPU rises when collections become frequent, often only late in the incident. Before that, CPU can look only moderately high.

A restart drops RSS immediately. If the same slope returns, the process is retaining objects again. Treat the restart as a way to restore latency, and keep a heap dump from before the next crash. A dump taken after the process has already been OOM-killed rarely contains the retained set.

## Retained objects and caches

Growth that survives GC usually means objects are still reachable. Common sources are a map with no eviction, session state that is never expired, listeners registered on every request, and a cache key that includes a unique id so entries never match. A library upgrade can retain listeners or buffers the previous version released.

These failures often look like latency first. Requests slow down as pauses grow. Errors, allocation failures, or restarts arrive later. Database connection utilization often stays well below its cap, because the process is busy in GC rather than waiting on the pool. A modest error rate at the end of a long memory climb is not, by itself, evidence of a dependency timeout.

## Latency under memory pressure

As free heap shrinks, the runtime collects more often and pauses get longer. p95 latency tracks memory rather than a sudden jump in traffic. Callers see timeouts and 5xx once pauses exceed their deadlines. Those timeouts can resemble a slow dependency if the investigation looks only at caller errors. The local signal is the memory slope and the GC messages on the same instance. Downstream latency, if it moves, usually moves because callers are waiting on the slow instance, not because a remote host changed.

## What to check during an incident

Plot memory over a long window, at least the length of the climb, and plot latency on the same chart. Check GC logs, heap warnings, allocation failures, and restarts. Check that request rate did not rise in proportion to memory. Check database connection utilization and downstream latency so a pool or dependency problem is not missed, and expect those series to stay nearer baseline when memory is the series that moved.

Immediate mitigation is often a restart or a rollback of the library or feature flag that started the slope. The durable change is eviction, a session cap, or a patched library, plus an alert on the slope of RSS rather than only on an out-of-memory kill.
