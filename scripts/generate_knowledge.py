#!/usr/bin/env python3
"""Build the historical-incident knowledge base (Day 7).

    python scripts/generate_knowledge.py          # seed 7, writes knowledge/incidents/

These records are synthetic postmortems. They are not copies of the INC-* evaluation set and
must not be used as current-incident evidence. Retrieval is out of scope for this script.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "knowledge" / "incidents"

DB = "DB_CONNECTION_POOL_EXHAUSTION"
MEM = "MEMORY_LEAK"
DOWN = "DOWNSTREAM_SERVICE_TIMEOUT"
DB_CLIENTS = ("orders-api", "payment-api", "inventory-service", "recommendation-service")
SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
LABELS = (DB, MEM, DOWN)
FORBIDDEN_NARRATIVE = re.compile(
    r"DB_CONNECTION_POOL_EXHAUSTION|MEMORY_LEAK|DOWNSTREAM_SERVICE_TIMEOUT|"
    r"\bmemory leak\b|\bpool exhaust",
    re.IGNORECASE,
)
NARRATIVE_FIELDS = ("title", "symptoms", "observed_signals", "timeline", "tags")


def pick(rng: random.Random, seq):
    return rng.choice(seq)


def sample(rng: random.Random, seq, k: int):
    return rng.sample(list(seq), k=min(k, len(seq)))


def balanced(rng: random.Random, options, n: int):
    out, opts = [], list(options)
    while len(out) < n:
        rng.shuffle(opts)
        out.extend(opts)
    rng.shuffle(out)
    return out[:n]


def occurred_at(rng: random.Random) -> str:
    """All historical dates fall before the evaluation dataset (2026-01-08)."""
    start = datetime(2024, 3, 1, 8, 0, 0)
    end = datetime(2025, 12, 20, 22, 0, 0)
    delta = int((end - start).total_seconds())
    t = start + timedelta(seconds=rng.randint(0, delta))
    t = t.replace(minute=rng.choice((0, 5, 12, 18, 27, 33, 41, 48, 55)), second=rng.randint(0, 59))
    return t.isoformat()


def rel(minutes: int) -> str:
    if minutes == 0:
        return "00m"
    sign = "-" if minutes < 0 else "+"
    m = abs(minutes)
    if m >= 60:
        h, rem = divmod(m, 60)
        return f"{sign}{h:02d}h{rem:02d}m" if rem else f"{sign}{h:02d}h"
    return f"{sign}{m:02d}m"


def uniq(items):
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def leak_scan(record: dict) -> list[str]:
    hits = []
    for field in NARRATIVE_FIELDS:
        value = record[field]
        text = json.dumps(value) if not isinstance(value, str) else value
        if FORBIDDEN_NARRATIVE.search(text):
            hits.append(field)
    for field, value in record.items():
        if field == "root_cause":
            continue
        text = json.dumps(value) if not isinstance(value, str) else value
        if any(label in text for label in LABELS):
            hits.append(field)
    return hits


# --------------------------------------------------------------------------- phrase banks (observable language only)


DB_TITLES = (
    "{svc}: elevated latency and 5xx during {when}",
    "Checkout errors while {svc} waited on the database",
    "SLO burn on {svc} with connection wait events",
    "{svc} p95 climbed and clients saw timeouts",
    "Intermittent 503s from {svc} under {when}",
    "On-call: {svc} error budget burn, database waits in logs",
    "Degraded {what} — {svc} saturating outbound DB calls",
    "{svc} alerted on latency; callers reported failed requests",
)
MEM_TITLES = (
    "{svc} slowed over the afternoon with rising RSS",
    "Gradual latency climb on {svc} then 5xx",
    "{svc} restarted after heap pressure, errors followed",
    "Pager: {svc} p95 and memory both off baseline",
    "Customer reports of timeouts while {svc} GC pauses grew",
    "{svc} became unstable after a several-hour memory climb",
    "Degraded {what}: {svc} latency tracked memory usage",
    "On-call notes: {svc} allocation failures near the end of the window",
)
DOWN_TITLES = (
    "{svc} 5xx while {dep} responses stalled",
    "Timeouts calling {dep} from {svc}",
    "{svc} error-rate SLO burn; upstream {dep} slow",
    "Checkout failures: {svc} waiting on {dep}",
    "Intermittent {what} — {svc} hitting client timeouts to {dep}",
    "Synthetic monitor: {svc} p95 vs {dep} deadline",
    "{svc} retries exhausted against {dep}",
    "Customers saw pending {what}; {svc} logged read timeouts",
)

WHEN = ("peak traffic", "the evening sale", "a batch window", "weekday lunch",
        "a marketing campaign", "month-end close", "a retry storm")
WHAT = ("checkout", "recommendations", "payments", "stock lookups", "cart updates", "order create")

DB_SYMPTOMS = (
    "threads waiting to acquire a database connection",
    "connection-acquisition timeouts in service logs",
    "pool wait count climbing on the affected service",
    "SQLAlchemy/Hikari/Knex timeout acquiring a connection",
    "database wait events coinciding with the latency climb",
)
MEM_SYMPTOMS = (
    "process memory usage climbing for tens of minutes",
    "longer GC or heap-pressure warnings",
    "RSS well above the usual band for that service",
    "occasional allocation failures or container restarts late in the incident",
    "latency growing in step with memory, not with a sudden traffic spike",
)
DOWN_SYMPTOMS = (
    "outbound calls to a dependency approaching the client timeout",
    "read/connect timeouts naming a downstream host",
    "circuit breaker or retry storms toward one dependency",
    "downstream p95 much higher than in-process work",
    "dependency health checks failing or degrading",
)
AMBIGUOUS_EXTRA = (
    "callers also logged upstream timeouts (looked like a dependency issue)",
    "modest rise in CPU while requests queued",
    "brief increase in held database connections while waiting on I/O",
    "memory moved a few percentage points but stayed far from the limit",
    "gateway returned 502/504 for a subset of routes",
)

DB_SIGNALS = (
    "db_connection_utilization on the service rose from a mid-20s baseline toward saturation",
    "connection wait time increased before error rate peaked",
    "latency jumped by more than 10x while CPU stayed only moderately higher",
    "memory stayed near baseline",
    "pool stats showed checked-out connections near max with a wait queue",
    "timeout-related WARN/ERROR rate on the service rose from near zero",
)
MEM_SIGNALS = (
    "memory_usage rose smoothly over a long period rather than in a single jump",
    "GC pause time and heap-used warnings increased with memory",
    "latency correlated with memory; errors arrived later",
    "db_connection_utilization stayed well below saturation",
    "after a restart, memory dropped and then began climbing again",
    "CPU increased only moderately until GC became frequent",
)
DOWN_SIGNALS = (
    "downstream_latency_ms on the caller rose toward the configured client timeout",
    "caller CPU and memory stayed close to baseline",
    "error rate rose after outbound calls started timing out",
    "timeout logs named a specific dependency, not the local database",
    "retries increased request rate slightly without a user-traffic surge",
    "db utilization rose only where the caller held connections during the wait",
)

DB_SCENARIOS = {
    "connection_leak": {
        "factors": (
            "a recent deploy introduced a path that did not close connections",
            "concurrency was higher than the pool was sized for",
        ),
        "resolution": (
            "rolled back the release that stopped returning connections to the pool",
            "enabled pool leak detection and added a saturation alert at 80%",
            "confirmed wait queue dropped after the rollback",
        ),
        "lessons": (
            "do not raise pool size without checking for leaks",
            "alert on pool utilization and acquire timeouts, not only on 5xx",
        ),
        "lead": "a deploy finished on {svc}",
    },
    "slow_query": {
        "factors": (
            "a missing index plus lock waits held connections for seconds",
            "the acquire timeout was shorter than the slow query",
        ),
        "resolution": (
            "terminated the long-running query and added an index plus statement_timeout",
            "cleared lock contention on the hot table",
            "documented the query in the runbook",
        ),
        "lessons": (
            "statement_timeout would have bounded the lock hold time",
            "treat connection-wait logs as a first-class signal during latency incidents",
        ),
        "lead": "traffic was unremarkable until a heavy query pattern hit {svc}",
    },
    "traffic_surge": {
        "factors": (
            "organic traffic plus retries exceeded the configured pool",
            "HPA lagged the traffic ramp",
        ),
        "resolution": (
            "raised Hikari/Knex/SQLAlchemy max pool size after reviewing concurrency",
            "killed sessions stuck in idle-in-transaction",
            "added dashboards for wait_count and acquire timeout rate",
        ),
        "lessons": (
            "alert on pool utilization and acquire timeouts, not only on 5xx",
            "treat connection-wait logs as a first-class signal during latency incidents",
        ),
        "lead": "traffic began rising on {svc}",
    },
    "pool_misconfig": {
        "factors": (
            "a config reload halved max pool size",
            "no alert existed on utilization before 5xx",
        ),
        "resolution": (
            "reverted the pool-size config change that had shrunk max connections",
            "required a review for pool settings in the next deploy",
            "paged on utilization remaining above 90% for 5 minutes",
        ),
        "lessons": (
            "do not raise pool size without checking for leaks",
            "alert on pool utilization and acquire timeouts, not only on 5xx",
        ),
        "lead": "a config reload ran on {svc}",
    },
}

MEM_SCENARIOS = {
    "unbounded_cache": {
        "factors": (
            "an in-process cache had no eviction policy",
            "the growth was slow enough that a 15-minute baseline looked almost normal at first",
        ),
        "resolution": (
            "restarted the affected deployment as immediate mitigation",
            "identified an unbounded in-process cache with no TTL",
            "shipped a hotfix with eviction and a heap-growth alert",
        ),
        "lessons": (
            "caches without TTL belong on the review checklist for every service",
            "a restart that restores latency is mitigation, not a fix",
        ),
        "lead": "a deploy or flag change on {svc} that populated a new cache",
    },
    "session_retention": {
        "factors": (
            "server-side sessions accumulated for users who never logged out",
            "the memory limit was close to the working set even when healthy",
        ),
        "resolution": (
            "cleared server-side sessions that were never expired",
            "set a max session map size",
            "restarted pods that had already crossed 90% RSS",
        ),
        "lessons": (
            "page on sustained memory slope, not only on OOM",
            "a restart that restores latency is mitigation, not a fix",
        ),
        "lead": "traffic was unremarkable at the start",
    },
    "library_regression": {
        "factors": (
            "a library upgrade retained objects that should have been released",
            "GC hid the problem until pauses became visible",
        ),
        "resolution": (
            "rolled back the library version that retained extra objects",
            "captured a heap dump before the second restart",
            "added a slow memory-growth monitor (15-minute slope)",
        ),
        "lessons": (
            "heap dumps need to be taken before the second crash",
            "page on sustained memory slope, not only on OOM",
        ),
        "lead": "a library bump shipped on {svc}",
    },
    "listener_leak": {
        "factors": (
            "a library upgrade retained event listeners",
            "no SLO existed on RSS slope",
        ),
        "resolution": (
            "rolled back the library version that retained listeners",
            "captured a heap dump before the second restart",
            "added a slow memory-growth monitor (15-minute slope)",
        ),
        "lessons": (
            "heap dumps need to be taken before the second crash",
            "a restart that restores latency is mitigation, not a fix",
        ),
        "lead": "a deploy finished on {svc}",
    },
}

DOWN_SCENARIOS = {
    "provider_degraded": {
        "factors": (
            "{dep} was degraded in one region",
            "{svc} timeout was tight relative to the provider p99",
        ),
        "resolution": (
            "confirmed {dep} latency on the provider status page and their dashboards",
            "raised the client timeout only after proving the dependency was the bottleneck",
            "enabled a circuit breaker and a cached fallback for non-critical reads",
        ),
        "lessons": (
            "distinguish caller CPU/memory (flat) from outbound latency (up)",
            "fallback and circuit breaking should be tested, not only documented",
        ),
        "lead": "synthetic checks to {dep} were still green",
    },
    "network_latency": {
        "factors": (
            "cross-zone latency to {dep} crossed the client deadline",
            "no hedged requests were configured",
        ),
        "resolution": (
            "investigated cross-zone RTT and packet loss toward {dep}",
            "pinned traffic to the healthy zone while the path was repaired",
            "recorded the timeout histogram in the incident ticket",
        ),
        "lessons": (
            "distinguish caller CPU/memory (flat) from outbound latency (up)",
            "retry storms can look like a traffic surge on the caller",
        ),
        "lead": "no local deploy on {svc}",
    },
    "dependency_overloaded": {
        "factors": (
            "a batch job on {dep} consumed the dependency's capacity",
            "caller retries multiplied load",
        ),
        "resolution": (
            "paused the batch job that was overloading {dep}",
            "spread the job and added a shared rate limit",
            "documented the dependency SLO in the caller runbook",
        ),
        "lessons": (
            "retry storms can look like a traffic surge on the caller",
            "held DB connections during a slow downstream call are a side effect of waiting, not a saturated local pool",
        ),
        "lead": "a batch window started on {dep}",
    },
    "dependency_slow": {
        "factors": (
            "{dep} thread pool saturated",
            "the caller had no fallback for that route",
        ),
        "resolution": (
            "capped retries to stop amplifying load on {dep}",
            "worked with the dependency owners on saturation of their pool",
            "added synthetic checks against {dep} from the same region",
        ),
        "lessons": (
            "fallback and circuit breaking should be tested, not only documented",
            "held DB connections during a slow downstream call are a side effect of waiting, not a saturated local pool",
        ),
        "lead": "no local deploy on {svc}",
    },
}

DB_TAGS = (
    ("database", "latency", "connections", "timeouts"),
    ("postgres", "5xx", "pool", "checkout"),
    ("latency", "wait-events", "slo", "database"),
    ("connections", "retries", "p95", "errors"),
)
MEM_TAGS = (
    ("memory", "gc", "latency", "rss"),
    ("heap", "5xx", "restart", "slo"),
    ("latency", "allocation", "process", "errors"),
    ("rss", "timeouts", "gc-pauses", "stability"),
)
DOWN_TAGS = (
    ("timeouts", "dependency", "latency", "5xx"),
    ("retries", "upstream", "slo", "p95"),
    ("circuit-breaker", "outbound", "errors", "latency"),
    ("dependency", "read-timeout", "gateway", "retries"),
)

CALLERS = {
    "orders-api": ("api-gateway", "checkout clients"),
    "payment-api": ("orders-api", "api-gateway"),
    "inventory-service": ("orders-api", "api-gateway"),
    "recommendation-service": ("api-gateway", "home-page clients"),
    "api-gateway": ("mobile app", "web spa"),
}


def db_record(rng, spec):
    svc, variant = spec["service"], spec["variant"]
    scene = DB_SCENARIOS[variant]
    when, what = pick(rng, WHEN), pick(rng, WHAT)
    title = pick(rng, DB_TITLES).format(svc=svc, when=when, what=what)
    symptoms = [
        pick(rng, ("elevated p95 latency on the alerting service",
                   "request latency well above the usual band",
                   "p95 and p99 latency climbing together")),
        pick(rng, ("increase in 5xx responses seen by callers",
                   "elevated 5xx rate on the alerting service",
                   "callers receiving 502/503/504 responses")),
        *sample(rng, DB_SYMPTOMS, 2),
    ]
    if spec["ambiguous"]:
        symptoms.append(pick(rng, AMBIGUOUS_EXTRA))
    rng.shuffle(symptoms)
    signals = sample(rng, DB_SIGNALS, 4)
    if spec["ambiguous"]:
        signals.append("downstream_latency_ms on callers increased as they waited on " + svc)
    dur = rng.choice((18, 24, 31, 37, 44, 52, 61))
    t0 = rng.choice((-8, -6, -5, -4))
    t_wait = t0 + rng.randint(2, 5)
    timeline = [
        {"relative_time": rel(t0 - rng.randint(8, 20)),
         "event": scene["lead"].format(svc=svc)},
        {"relative_time": rel(t0),
         "event": pick(rng, ("p95 latency on " + svc + " began climbing",
                             "request duration histograms shifted right on " + svc))},
        {"relative_time": rel(t_wait),
         "event": pick(rng, ("connection wait logs appeared on " + svc,
                             "pool stats showed a wait queue on " + svc))},
        {"relative_time": "00m",
         "event": pick(rng, ("5xx / error-rate alert fired on " + spec["alerting"],
                             "SLO burn page for " + spec["alerting"]))},
        {"relative_time": rel(rng.randint(8, 20)),
         "event": pick(rng, ("mitigation applied; latency and waits receded",
                             "error rate returned toward baseline after the change"))},
    ]
    extras = ["database", *list(CALLERS.get(svc, ()))[:2]]
    return dict(title=title, symptoms=symptoms, observed_signals=signals, timeline=timeline,
                contributing_factors=list(scene["factors"]), resolution=list(scene["resolution"]),
                lessons_learned=list(scene["lessons"]), tags=list(pick(rng, DB_TAGS)),
                duration_minutes=dur, extra_services=extras)


def mem_record(rng, spec):
    svc, variant = spec["service"], spec["variant"]
    scene = MEM_SCENARIOS[variant]
    what = pick(rng, WHAT)
    title = pick(rng, MEM_TITLES).format(svc=svc, what=what)
    symptoms = [
        pick(rng, ("elevated p95 latency on the alerting service",
                   "latency growing in step with memory, not with a sudden traffic spike",
                   "request duration stretching over the afternoon")),
        pick(rng, ("increase in 5xx responses seen by callers",
                   "errors appearing late in the window after a long slow period",
                   "callers seeing timeouts and 5xx once the process was under heap pressure")),
        *sample(rng, MEM_SYMPTOMS, 2),
    ]
    if spec["ambiguous"]:
        symptoms.append(pick(rng, ("timeouts that could be mistaken for a slow dependency",
                                   "5xx without an obvious connection-wait signature at first glance")))
    rng.shuffle(symptoms)
    signals = sample(rng, MEM_SIGNALS, 4)
    if spec["ambiguous"]:
        signals.append("db_connection_utilization stayed below 60% throughout")
    dur = rng.choice((28, 36, 45, 54, 67, 88, 102))
    climb = rng.choice((-70, -55, -40, -35))
    timeline = [
        {"relative_time": rel(climb - rng.randint(5, 15)),
         "event": scene["lead"].format(svc=svc)},
        {"relative_time": rel(climb),
         "event": "memory_usage on " + svc + " began a near-linear climb"},
        {"relative_time": rel(climb + rng.randint(15, 35)),
         "event": pick(rng, ("GC / heap warnings became frequent on " + svc,
                             "p95 latency on " + svc + " moved with memory"))},
        {"relative_time": "00m",
         "event": pick(rng, ("error-rate or latency alert fired on " + spec["alerting"],
                             spec["alerting"] + " started returning 5xx to callers"))},
        {"relative_time": rel(rng.randint(10, 25)),
         "event": pick(rng, ("restart or rollback dropped RSS; latency followed",
                             "a second climb started until the code fix landed"))},
    ]
    return dict(title=title, symptoms=symptoms, observed_signals=signals, timeline=timeline,
                contributing_factors=list(scene["factors"]), resolution=list(scene["resolution"]),
                lessons_learned=list(scene["lessons"]), tags=list(pick(rng, MEM_TAGS)),
                duration_minutes=dur, extra_services=list(CALLERS.get(svc, ()))[:2])


def down_record(rng, spec):
    svc, dep, variant = spec["service"], spec["dep"], spec["variant"]
    scene = DOWN_SCENARIOS[variant]
    what = pick(rng, WHAT)
    title = pick(rng, DOWN_TITLES).format(svc=svc, dep=dep, what=what)
    symptoms = [
        pick(rng, ("elevated p95 latency on the alerting service",
                   "end-to-end latency dominated by waiting on a dependency",
                   "request latency well above the usual band")),
        pick(rng, ("increase in 5xx responses seen by callers",
                   "elevated 5xx rate on the alerting service",
                   "callers receiving 502/503/504 responses")),
        *sample(rng, DOWN_SYMPTOMS, 2),
    ]
    if spec["ambiguous"]:
        symptoms.append(pick(rng, AMBIGUOUS_EXTRA))
    rng.shuffle(symptoms)
    signals = sample(rng, DOWN_SIGNALS, 4)
    ctx = {"svc": svc, "dep": dep}
    factors = [s.format(**ctx) for s in scene["factors"]]
    res = [s.format(**ctx) for s in scene["resolution"]]
    dur = rng.choice((16, 22, 29, 35, 41, 48, 55))
    t0 = rng.choice((-6, -4, -3, -2))
    timeline = [
        {"relative_time": rel(t0 - rng.randint(4, 12)),
         "event": scene["lead"].format(**ctx)},
        {"relative_time": rel(t0),
         "event": pick(rng, ("outbound p95 from " + svc + " toward " + dep + " rose",
                             svc + " began retrying calls to " + dep))},
        {"relative_time": rel(t0 + rng.randint(1, 3)),
         "event": pick(rng, ("client-timeout errors named " + dep,
                             "circuit breaker or retry logs referenced " + dep))},
        {"relative_time": "00m",
         "event": pick(rng, ("5xx alert fired on " + spec["alerting"],
                             "customers reported failed " + what))},
        {"relative_time": rel(rng.randint(6, 18)),
         "event": pick(rng, (dep + " recovered or was isolated; caller errors receded",
                             "fallback served cached responses until " + dep + " recovered"))},
    ]
    extras = [dep] + list(CALLERS.get(svc, ()))[:1]
    return dict(title=title, symptoms=symptoms, observed_signals=signals, timeline=timeline,
                contributing_factors=factors, resolution=res,
                lessons_learned=list(scene["lessons"]),
                tags=list(pick(rng, DOWN_TAGS)) + [dep.split("-")[0]], duration_minutes=dur,
                extra_services=extras)


def plan(seed: int) -> list[dict]:
    rng = random.Random(seed)
    specs = []
    db_services = balanced(rng, DB_CLIENTS, 10)
    db_variants = balanced(rng, ("connection_leak", "slow_query", "traffic_surge", "pool_misconfig"), 10)
    mem_services = balanced(rng, DB_CLIENTS, 10)
    mem_variants = balanced(rng, ("unbounded_cache", "session_retention", "library_regression", "listener_leak"), 10)
    down_pairs = balanced(rng, (
        ("payment-api", "acquirer-gateway", "provider_degraded"),
        ("inventory-service", "warehouse-api", "provider_degraded"),
        ("orders-api", "inventory-service", "dependency_slow"),
        ("orders-api", "inventory-service", "network_latency"),
        ("api-gateway", "recommendation-service", "dependency_overloaded"),
        ("orders-api", "payment-api", "dependency_slow"),
        ("api-gateway", "orders-api", "dependency_slow"),
        ("payment-api", "acquirer-gateway", "network_latency"),
        ("inventory-service", "warehouse-api", "dependency_overloaded"),
        ("api-gateway", "payment-api", "provider_degraded"),
    ), 10)
    sevs_db = balanced(rng, SEVERITIES, 10)
    sevs_mem = balanced(rng, SEVERITIES, 10)
    sevs_dn = balanced(rng, SEVERITIES, 10)
    for i in range(10):
        alerter = db_services[i] if rng.random() < 0.7 else pick(rng, ("api-gateway", "orders-api", db_services[i]))
        specs.append({"root_cause": DB, "service": db_services[i], "alerting": alerter,
                      "variant": db_variants[i], "severity": sevs_db[i], "dep": None,
                      "ambiguous": i < 3, "build": db_record})
    for i in range(10):
        alerter = mem_services[i] if rng.random() < 0.6 else pick(rng, ("api-gateway", mem_services[i]))
        specs.append({"root_cause": MEM, "service": mem_services[i], "alerting": alerter,
                      "variant": mem_variants[i], "severity": sevs_mem[i], "dep": None,
                      "ambiguous": i < 3, "build": mem_record})
    for i in range(10):
        svc, dep, variant = down_pairs[i]
        specs.append({"root_cause": DOWN, "service": svc, "alerting": svc, "variant": variant,
                      "severity": sevs_dn[i], "dep": dep, "ambiguous": i < 3, "build": down_record})
    rng.shuffle(specs)
    for i, spec in enumerate(specs, start=1):
        spec["incident_id"] = f"HIST-{i:03d}"
    return specs


def assemble(rng: random.Random, spec: dict) -> dict:
    body = spec["build"](rng, spec)
    affected = []
    for name in (spec["alerting"], spec["service"], *body["extra_services"]):
        if name and name not in affected:
            affected.append(name)
    record = {
        "incident_id": spec["incident_id"],
        "title": body["title"],
        "occurred_at": occurred_at(rng),
        "service": spec["alerting"],
        "root_cause_service": spec["service"],
        "severity": spec["severity"],
        "duration_minutes": body["duration_minutes"],
        "environment": "production",
        "status": "resolved",
        "symptoms": uniq(body["symptoms"]),
        "observed_signals": uniq(body["observed_signals"]),
        "timeline": body["timeline"],
        "root_cause": spec["root_cause"],
        "contributing_factors": body["contributing_factors"],
        "resolution": body["resolution"],
        "lessons_learned": body["lessons_learned"],
        "tags": uniq(body["tags"]),
        "affected_services": affected,
    }
    leaks = leak_scan(record)
    if leaks:
        raise ValueError(f"{spec['incident_id']}: forbidden phrasing in {leaks}")
    return record


def uniquify_titles(records: list[dict]) -> None:
    seen: set[str] = set()
    for record in records:
        title = record["title"]
        if title in seen:
            stamp = datetime.fromisoformat(record["occurred_at"]).strftime("%b %Y")
            title = f"{title} ({stamp})"
            if title in seen:
                title = f"{title[:-1]}, {record['duration_minutes']}m)"
        record["title"] = title
        seen.add(title)
        leaks = leak_scan(record)
        if leaks:
            raise ValueError(f"{record['incident_id']}: forbidden phrasing in {leaks}")


def generate(seed: int = 7, output_dir: Path = DEFAULT_OUT) -> list[dict]:
    rng = random.Random(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    for leftover in output_dir.glob("HIST-*.json"):
        leftover.unlink()
    records = [assemble(rng, spec) for spec in plan(seed)]
    uniquify_titles(records)
    index = []
    for record in records:
        path = output_dir / f"{record['incident_id']}.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        index.append({"incident_id": record["incident_id"], "root_cause": record["root_cause"],
                      "service": record["service"], "severity": record["severity"],
                      "occurred_at": record["occurred_at"]})
    manifest = {"generator": "scripts/generate_knowledge.py", "seed": seed, "count": len(records),
                "by_root_cause": {k: sum(1 for r in records if r["root_cause"] == k)
                                  for k in (DB, MEM, DOWN)},
                "incidents": index}
    (output_dir.parent / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    records = generate(args.seed, args.output_dir)
    counts = {k: sum(1 for r in records if r["root_cause"] == k) for k in (DB, MEM, DOWN)}
    print(f"Wrote {len(records)} historical incidents to {args.output_dir} (seed={args.seed})")
    for k, n in counts.items():
        print(f"  {k}: {n}")
    print(f"  unique titles: {len({r['title'] for r in records})}")
    print(f"  services: {sorted({r['service'] for r in records})}")
    print(f"  date span: {min(r['occurred_at'] for r in records)[:10]} .. {max(r['occurred_at'] for r in records)[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
