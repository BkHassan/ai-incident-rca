# Downstream latency, timeouts, and dependency health

A caller spends part of every request waiting on other services. That wait is visible as downstream latency, distinct from time spent in local CPU or the local database pool. When the dependency slows down or stops answering, the caller times out, retries, and returns errors to its own clients.

## Downstream latency

Downstream latency is the time from the caller's outbound request until the dependency responds or the client gives up. It should sit well under the configured client timeout, with a small tail. A rise in that series, while the caller's CPU and memory stay near baseline, usually means the time is being spent off-box.

Name the dependency in the logs. Payment traffic often calls an acquirer. Inventory traffic often calls a warehouse API. Orders traffic calls inventory and payments. The gateway calls several of those services. A timeout line that names one host is more specific than a generic 5xx on the gateway. Gateway 502 and 504 responses are what clients see after an upstream deadline is missed.

## Timeouts, retries, and amplification

A client timeout fires when the dependency exceeds the caller's deadline. Connect timeouts and read timeouts are different: one means the TCP session was not established, the other means the peer accepted the connection and then stalled. Either one is a caller-side observation. It does not by itself prove the dependency process has crashed. The network path, a saturated thread pool on the dependency, or a regional degradation can produce the same client error.

Retries help a short blip and hurt a sustained slowdown. Each failed attempt adds load on the dependency and holds a caller thread, and sometimes a database connection, until the retry budget is exhausted. Request rate on the caller can rise slightly with no extra user traffic. That pattern is a retry storm, not a demand spike. Capping retries, or backing off, stops the amplification. Raising the client timeout hides the symptom only after measurements show the dependency is the slow side and the extra wait is acceptable.

## Circuit breakers and fallbacks

A circuit breaker opens after a run of failures or slow calls and then fails fast, or serves a fallback, instead of waiting for the full timeout. Logs show state changes, ejected hosts, and fallback responses. An open breaker is a protective reaction. The underlying dependency latency is still the condition to explain.

Fallbacks (cached reads, default recommendations, a queued payment) keep a non-critical path up. They should be tested. A fallback that still calls the sick dependency does not help. Synthetic checks from the same region as the caller show whether the dependency is slow from that network, which a status page written in another region can miss.

## Dependency health versus local resources

Compare three series on the caller: CPU, memory, and downstream latency. Flat CPU and memory with downstream latency near the client timeout point away from a local memory climb. Database connection utilization can rise a few points because the caller holds a connection while it waits on the dependency. That rise is a side effect of the wait. It is not the same pattern as utilization pinned at the pool maximum with acquire timeouts and no slow dependency.

On the dependency, look for its own saturation: thread pool, connection pool, or a batch job that consumed its capacity. Cross-zone packet loss and RTT show up as timeouts without a deploy on the caller. A batch window that starts on the dependency, with no local deploy on the caller, is a useful time marker. It is still a marker, not proof, until the dependency's own metrics agree.

## What to check during an incident

Start with the timeout logs and the name of the host they mention. Check downstream latency against the client timeout, then retries and breaker state. Check caller CPU and memory. Check whether database connections are merely held during the wait or are actually exhausted. Talk to the dependency's dashboards or status page before widening the caller's timeout. Durable changes are a bounded retry policy, a breaker, a fallback on non-critical reads, and a synthetic check beside the caller's region.
