# Database connections, pools, and slow queries

Application services usually borrow a database connection from a pool, run a statement, and return the connection. Latency, error rate, and pool statistics have to be read together. A rise in errors alone does not say whether the database, the pool, or a caller is at fault.

## Connection pools

A pool caps how many sessions one process may hold. Typical settings are a maximum size, a minimum idle set, and a timeout for borrowing a connection. Java services often use HikariCP. Python services often use SQLAlchemy or psycopg pools. Node services often use Knex or `pg`. The database server has its own `max_connections`, shared by every client.

Healthy utilization sits well below the cap, with a short wait to borrow a connection and almost no acquire timeouts. The idle count moves as traffic moves. A deploy that opens a session per request, or that forgets to close a session on an error path, changes those numbers even when query volume does not.

## Saturation and maximum connections

Saturation means checked-out connections sit at the configured maximum and new work queues. Client metrics to watch are utilization (checked out divided by max), wait count, and threads blocked in acquisition. On the server, watch active backends against `max_connections`, and sessions stuck `idle in transaction`.

Utilization in the mid-20s to mid-40s percent is a common baseline for these services. A climb toward 90 percent and above, held for minutes, is a capacity problem even before requests fail. Raising `max_connections` or the client pool size absorbs a real traffic increase. It hides a leak: the extra sessions are still never returned. Compare utilization with request rate. If utilization rises while request rate does not, suspect held connections or a slow statement, not a traffic spike.

## Acquisition timeouts

When the wait exceeds the pool's acquire timeout, the request fails in the application. Logs look like "timeout acquiring a connection", a pool exhausted message, or a client library timeout, often with no SQL error from the server. Those failures show up as 5xx to callers. Latency rises first, because requests sit in the wait queue, and the error rate peaks later.

Distinguish this from a statement timeout. An acquire timeout happens before the query is sent. A statement timeout happens after a connection was borrowed. Both increase latency. Only the acquire timeout, together with a full pool, points at pool capacity or connections that were not released.

## Slow queries and lock waits

A query that holds its connection for seconds reduces the pool even when the pool size is unchanged. Missing indexes, lock waits, and idle-in-transaction sessions are typical reasons. Server logs and views such as `pg_stat_activity` show the waiting query and the blocker. Client logs show slow-query warnings with a duration.

If one statement is slow, other requests pile up behind it and the pool wait metric climbs. CPU on the database may rise only modestly. Memory on the application stays near its baseline, because the threads are blocked, not allocating. Killing the blocker, adding an index, or setting `statement_timeout` returns connections to the pool. Increasing the pool without bounding the statement moves the same queue into a larger one.

## What to check during an incident

Read the series in order. Latency and error rate say the service is unhealthy. Database connection utilization, acquire timeouts, and pool wait logs say connections are the scarce resource. Downstream latency and process memory staying near baseline make an unrelated dependency or a memory climb less likely, but a modest CPU increase is common whenever requests queue and does not identify the pool by itself.

Confirm whether a deploy, config reload, or traffic change preceded the climb. A smaller max pool size after a reload looks like saturation with no extra user traffic. A leak looks like a gradual climb after a release, with connections not returning when traffic dips. A slow query looks like wait events and lock holders on one statement. Dashboards that alert on utilization and acquire timeouts, not only on 5xx, surface the condition before the error budget is gone.
