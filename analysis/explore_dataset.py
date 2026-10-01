#!/usr/bin/env python3
"""Day 3: exploration and quality analysis of the synthetic incident dataset.

Read-only with respect to the dataset. Loads data/raw/{incidents,logs,metrics},
computes summary statistics and scenario checks, and writes:

    analysis/figures/*.png        plots
    analysis/results/*.csv|json   computed statistics
    analysis/results/tables.md    markdown tables used by docs/dataset_analysis.md

    python analysis/explore_dataset.py
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
FIG = ROOT / "analysis" / "figures"
RES = ROOT / "analysis" / "results"

DB, MEM, DOWN, NORMAL = ("DB_CONNECTION_POOL_EXHAUSTION", "MEMORY_LEAK", "DOWNSTREAM_SERVICE_TIMEOUT", "NORMAL")
SCENARIOS = (DB, MEM, DOWN, NORMAL)
SHORT = {DB: "DB pool", MEM: "Memory leak", DOWN: "Downstream timeout", NORMAL: "Normal"}
METRICS = ["cpu_usage", "memory_usage", "request_rate", "latency_ms", "error_rate",
           "db_connection_utilization", "downstream_latency_ms"]
LEVELS = ["INFO", "WARN", "ERROR"]
TIMEOUT_RE = re.compile(r"timed out|timeout|deadline exceeded", re.IGNORECASE)
LABEL_RE = re.compile(r"DB_CONNECTION_POOL_EXHAUSTION|MEMORY_LEAK|DOWNSTREAM_SERVICE_TIMEOUT|"
                      r"root[ _-]?cause|memory leak|pool exhaust", re.IGNORECASE)
KEYWORDS = {
    "timeout / timed out / deadline": TIMEOUT_RE,
    "'Database connection timeout'": re.compile(r"Database connection timeout"),
    "pool": re.compile(r"\bpool\b|QueuePool|HikariPool", re.IGNORECASE),
    "heap / GC": re.compile(r"\bheap\b|\bGC\b|\bgc\b|Mark-Compact|garbage", re.IGNORECASE),
    "OOM / out of memory": re.compile(r"OOM|out of memory|OutOfMemory|MemoryError", re.IGNORECASE),
    "HTTP 503 / 502 / 504": re.compile(r"\b50[234]\b"),
    "circuit breaker / ejecting": re.compile(r"circuit|ejecting", re.IGNORECASE),
    "retry": re.compile(r"retry|retrying", re.IGNORECASE),
}
DESCRIPTION_WORDS = ("pool", "connection", "memory", "leak", "heap", "oom", "garbage", "downstream",
                     "provider", "network", "dependency", "timing out", "timeout")
MIN = pd.Timedelta(minutes=1)


def normalize(message: str) -> str:
    message = re.sub(r"(?=[0-9a-f]*\d)[0-9a-f]{5,}", "#", message)
    return re.sub(r"\d+(\.\d+)?", "#", message)


# --------------------------------------------------------------------------- loading

def load():
    incidents = pd.DataFrame([json.loads(p.read_text(encoding="utf-8"))
                              for p in sorted((RAW / "incidents").glob("*.json"))])
    incidents = incidents.set_index("incident_id", drop=False)
    for col in ("start_time", "end_time", "window_start", "window_end", "fault_start_time"):
        incidents[col] = pd.to_datetime(incidents[col])
    incidents["focus"] = [r.root_cause_service if r.scenario in (DB, MEM) else r.service
                          for r in incidents.itertuples()]
    incidents["ref"] = incidents["fault_start_time"].fillna(incidents["start_time"])
    incidents["window_minutes"] = (incidents.window_end - incidents.window_start) / MIN

    metrics = pd.concat([pd.read_csv(p) for p in sorted((RAW / "metrics").glob("*.csv"))], ignore_index=True)
    metrics["timestamp"] = pd.to_datetime(metrics["timestamp"])

    logs = pd.concat([pd.read_json(p, lines=True, dtype=False, convert_dates=False)
                      for p in sorted((RAW / "logs").glob("*.jsonl"))], ignore_index=True)
    logs["timestamp"] = pd.to_datetime(logs["timestamp"])
    logs["template"] = logs["message"].map(normalize)
    logs["is_timeout"] = logs["message"].str.contains(TIMEOUT_RE)
    return incidents, metrics, logs


class Case:
    """Convenience accessors for one incident."""

    def __init__(self, meta, metrics, logs):
        self.meta = meta
        self.metrics = metrics
        self.logs = logs
        self.baseline = (meta.ref - pd.Timedelta(minutes=30), meta.ref - MIN)
        self.window = (meta.start_time, meta.end_time)

    def series(self, service):
        return self.metrics[self.metrics.service == service].set_index("timestamp")

    @staticmethod
    def between(df, lo, hi):
        return df[(df.index >= lo) & (df.index <= hi)]

    def base(self, service, col):
        return self.between(self.series(service), *self.baseline)[col].median()

    def peak(self, service, col, lo=None, hi=None):
        return self.between(self.series(service), lo or self.window[0], hi or self.window[1])[col].max()

    def onset(self, service, col, threshold, run=2):
        """Minutes after the reference time at which col stays above threshold for `run` minutes."""
        s = self.series(service)[col]
        s = s[s.index >= self.meta.ref - pd.Timedelta(minutes=5)]
        hits = (s > threshold).astype(int).rolling(run).sum()
        hits = hits[hits >= run]
        if hits.empty:
            return None
        return round((hits.index[0] - (run - 1) * MIN - self.meta.ref) / MIN, 1)

    def log_rate(self, mask, lo, hi):
        sel = self.logs[mask & (self.logs.timestamp >= lo) & (self.logs.timestamp <= hi)]
        return len(sel) / max(1.0, (hi - lo) / MIN)


# --------------------------------------------------------------------------- analysis

def dataset_summary(incidents, metrics, logs):
    return {
        "total_cases": int(len(incidents)),
        "cases_per_scenario": {s: int((incidents.scenario == s).sum()) for s in SCENARIOS},
        "failure_incidents": int((incidents.scenario != NORMAL).sum()),
        "log_records": int(len(logs)),
        "log_levels": {lv: int((logs.level == lv).sum()) for lv in LEVELS},
        "log_level_other": int((~logs.level.isin(LEVELS)).sum()),
        "metric_rows": int(len(metrics)),
        "metric_columns": list(metrics.columns),
        "services_in_metrics": sorted(metrics.service.unique()),
        "services_in_logs": sorted(logs.service.unique()),
        "date_range": [str(incidents.window_start.min()), str(incidents.window_end.max())],
        "blank_values": {c: int(metrics[c].isna().sum()) for c in METRICS},
        "blank_by_service": {c: sorted(metrics.loc[metrics[c].isna(), "service"].unique())
                             for c in METRICS if metrics[c].isna().any()},
    }


def metric_stats(incidents, cases):
    """Distribution of every metric on the focus service, before the fault vs. during the incident."""
    rows = []
    for scenario in SCENARIOS:
        for phase in ("baseline", "incident"):
            frames = []
            for iid in incidents.index[incidents.scenario == scenario]:
                c = cases[iid]
                lo, hi = c.baseline if phase == "baseline" else c.window
                frames.append(Case.between(c.series(c.meta.focus), lo, hi))
            df = pd.concat(frames)
            for col in METRICS:
                s = df[col].dropna()
                rows.append({"scenario": scenario, "phase": phase, "metric": col, "n": len(s),
                             "mean": s.mean(), "std": s.std(), "min": s.min(), "max": s.max()})
    return pd.DataFrame(rows)


def metric_stats_all_rows(incidents, metrics):
    df = metrics.merge(incidents[["scenario"]], left_on="incident_id", right_index=True)
    out = df.groupby("scenario")[METRICS].agg(["mean", "std", "min", "max"])
    return out.reindex(list(SCENARIOS))


def incident_signals(incidents, cases):
    """Per-case features measured the same way for every scenario (focus service unless noted)."""
    rows = []
    for iid, meta in incidents.iterrows():
        c, f, rep = cases[iid], meta.focus, meta.service
        r = {"incident_id": iid, "scenario": meta.scenario, "variant": meta.root_cause_variant,
             "service": rep, "focus": f, "severity": meta.severity, "duration_min": meta.duration_minutes,
             "window_min": meta.window_minutes,
             "fault_offset_min": (meta.ref - meta.window_start) / MIN,
             "alert_lag_min": (meta.start_time - meta.ref) / MIN}
        for col in METRICS:
            r[f"base_{col}"] = c.base(f, col)
            r[f"peak_{col}"] = c.peak(f, col)
        r["mem_rise"] = c.peak(f, "memory_usage", meta.ref, meta.end_time) - r["base_memory_usage"]
        r["latency_ratio"] = r["peak_latency_ms"] / r["base_latency_ms"]
        r["error_delta"] = r["peak_error_rate"] - r["base_error_rate"]
        r["cpu_ratio"] = r["peak_cpu_usage"] / r["base_cpu_usage"]
        r["request_rate_ratio"] = r["peak_request_rate"] / r["base_request_rate"]
        r["db_ratio"] = (r["peak_db_connection_utilization"] / r["base_db_connection_utilization"]
                         if pd.notna(r["base_db_connection_utilization"]) else np.nan)
        rep_base_ds = c.base(rep, "downstream_latency_ms")
        r["reported_ds_ratio"] = c.peak(rep, "downstream_latency_ms") / rep_base_ds if pd.notna(rep_base_ds) else np.nan
        r["reported_latency_ratio"] = c.peak(rep, "latency_ms") / c.base(rep, "latency_ms")
        r["reported_error_delta"] = c.peak(rep, "error_rate") - c.base(rep, "error_rate")
        r["max_error_any_service"] = Case.between(c.metrics.set_index("timestamp"), *c.window)["error_rate"].max()

        logs = c.logs
        r["log_records"] = len(logs)
        for lv in LEVELS:
            r[f"{lv.lower()}_logs"] = int((logs.level == lv).sum())
        r["info_share"] = r["info_logs"] / max(1, len(logs))
        r["warn_per_min_baseline"] = c.log_rate(logs.level == "WARN", *c.baseline)
        r["warn_per_min_incident"] = c.log_rate(logs.level == "WARN", *c.window)
        r["error_per_min_baseline"] = c.log_rate(logs.level == "ERROR", *c.baseline)
        r["error_per_min_incident"] = c.log_rate(logs.level == "ERROR", *c.window)
        timeout = logs.is_timeout & logs.level.isin(["WARN", "ERROR"])
        r["timeout_logs_incident"] = int((timeout & (logs.timestamp >= c.window[0]) & (logs.timestamp <= c.window[1])).sum())
        r["timeout_per_min_baseline"] = c.log_rate(timeout, *c.baseline)
        r["timeout_per_min_incident"] = c.log_rate(timeout, *c.window)

        # onsets (minutes after fault start) of the main signals, for event-ordering analysis
        b = {col: r[f"base_{col}"] for col in METRICS}
        r["onset_latency"] = c.onset(f, "latency_ms", 2 * b["latency_ms"])
        r["onset_error"] = c.onset(f, "error_rate", b["error_rate"] + 1.0)
        if meta.scenario == DB:
            r["onset_primary"] = c.onset(f, "db_connection_utilization", 85)
        elif meta.scenario == MEM:
            r["onset_primary"] = c.onset(f, "memory_usage", b["memory_usage"] + 10)
        elif meta.scenario == DOWN:
            r["onset_primary"] = c.onset(f, "downstream_latency_ms", 2 * b["downstream_latency_ms"])
        else:
            r["onset_primary"] = None
        after = logs[timeout & (logs.timestamp >= meta.ref - pd.Timedelta(minutes=5))]
        r["onset_timeout_log"] = round((after.timestamp.min() - meta.ref) / MIN, 1) if len(after) else None
        r["minutes_before_start_in_window"] = (meta.start_time - meta.window_start) / MIN

        if meta.scenario == MEM:
            r.update(memory_shape(c, f, meta))
            s = Case.between(c.series(f), meta.ref, meta.end_time)
            r["spearman_mem_latency"] = s["memory_usage"].corr(s["latency_ms"], method="spearman")
            r["oom_events"] = int(logs.message.str.contains("OOMKilled").sum())
        rows.append(r)
    return pd.DataFrame(rows).set_index("incident_id", drop=False)


def memory_shape(c, service, meta):
    """Linear-fit quality and largest single-minute step of the leak before the first restart."""
    s = Case.between(c.series(service), meta.ref, meta.end_time)["memory_usage"]
    drops = s.diff() < -15
    if drops.any():
        s = s[: drops.idxmax() - MIN]
    s = s[: s.idxmax()]
    x = np.asarray((s.index - s.index[0]) / MIN, dtype=float)
    slope, intercept = np.polyfit(x, s.values, 1)
    fitted = slope * x + intercept
    ss_res = float(((s.values - fitted) ** 2).sum())
    ss_tot = float(((s.values - s.values.mean()) ** 2).sum())
    rise = s.max() - s.iloc[0]
    return {"leak_minutes_to_peak": float(x[-1]), "leak_slope_pct_per_min": slope,
            "leak_linear_r2": 1 - ss_res / ss_tot if ss_tot else np.nan,
            "leak_max_step_share": s.diff().max() / rise if rise > 0 else np.nan}


def normal_checks(incidents, cases):
    rows = []
    for iid in incidents.index[incidents.scenario == NORMAL]:
        c = cases[iid]
        m = c.metrics
        longest = 0
        for _, g in m.groupby("service"):
            run = best = 0
            for v in g.sort_values("timestamp").error_rate:
                run = run + 1 if v > 2 else 0
                best = max(best, run)
            longest = max(longest, best)
        f = c.meta.focus
        fs = c.series(f)
        rows.append({
            "incident_id": iid, "blip": c.meta.root_cause_detail, "service": f,
            "max_error_rate_any": m.error_rate.max(), "longest_run_error_gt2pct_min": longest,
            "max_db_util_any": m.db_connection_utilization.max(),
            "focus_latency_cv": fs.latency_ms.std() / fs.latency_ms.mean(),
            "focus_latency_peak_ratio": c.peak(f, "latency_ms") / c.base(f, "latency_ms"),
            "focus_memory_range": fs["memory_usage"].max() - fs["memory_usage"].min(),
            "warn_logs": int((c.logs.level == "WARN").sum()),
            "error_logs": int((c.logs.level == "ERROR").sum()),
            "warn_per_min": (c.logs.level == "WARN").sum() / c.meta.window_minutes,
        })
    return pd.DataFrame(rows)


def template_analysis(incidents, logs):
    wl = logs[logs.level.isin(["WARN", "ERROR"])]
    presence = wl.groupby("template").incident_id.agg(lambda s: set(s))
    scen_of = incidents.scenario.to_dict()
    out = {}
    for scenario in SCENARIOS[:3]:
        inside = set(incidents.index[incidents.scenario == scenario])
        outside = set(incidents.index) - inside
        rows = []
        for tpl, ids in presence.items():
            rows.append({"template": tpl, "coverage_in": len(ids & inside) / len(inside),
                         "cases_outside": len(ids & outside)})
        df = pd.DataFrame(rows)
        excl = df[df.cases_outside == 0].sort_values("coverage_in", ascending=False).head(3)
        common = df.sort_values(["coverage_in", "cases_outside"], ascending=[False, True]).head(3)
        errs = logs[(logs.level == "ERROR") & logs.incident_id.isin(inside)]
        sets = errs.groupby("incident_id").template.agg(set)
        jacc = [len(a & b) / len(a | b) for a, b in itertools.combinations(sets.values, 2)]
        out[scenario] = {
            "unique_error_templates": int(errs.template.nunique()),
            "error_templates_per_incident": [int(len(s)) for s in sets.values],
            "pairwise_jaccard_mean": float(np.mean(jacc)), "pairwise_jaccard_max": float(np.max(jacc)),
            "templates_in_every_incident": int((df.coverage_in == 1.0).sum()),
            "templates_in_every_incident_and_nowhere_else": int(((df.coverage_in == 1.0) & (df.cases_outside == 0)).sum()),
            "best_exclusive": excl.to_dict("records"),
            "most_common": common.to_dict("records"),
        }
    keyword_rows = []
    for name, rx in KEYWORDS.items():
        hit = set(wl.loc[wl.message.str.contains(rx), "incident_id"])
        keyword_rows.append({"keyword": name, **{SHORT[s]: sum(1 for i in hit if scen_of[i] == s) /
                                                  (incidents.scenario == s).sum() for s in SCENARIOS}})
    return out, pd.DataFrame(keyword_rows)


def leakage_checks(incidents, metrics, logs):
    label_hits = int(logs.message.str.contains(LABEL_RE).sum())
    desc = []
    for s in SCENARIOS:
        sub = incidents[incidents.scenario == s]
        text = (sub.title + " " + sub.description).str.lower()
        desc.append({"scenario": SHORT[s], **{w: int(text.str.contains(re.escape(w)).sum()) for w in DESCRIPTION_WORDS}})
    dup = metrics.fillna({c: -1.0 for c in METRICS}).groupby(["service"] + METRICS).incident_id.nunique()
    return {"label_strings_in_logs": label_hits,
            "metric_rows_shared_by_multiple_incidents": int((dup > 1).sum()),
            "description_word_counts": desc}


def ordering_analysis(signals):
    out = {}
    for scenario in SCENARIOS[:3]:
        sub = signals[signals.scenario == scenario]
        orders, lags = [], {"latency": [], "error": [], "timeout_log": []}
        for _, r in sub.iterrows():
            events = {"primary": r.onset_primary, "latency": r.onset_latency, "error": r.onset_error}
            seen = {k: v for k, v in events.items() if v is not None and not pd.isna(v)}
            groups = {}
            for k, v in seen.items():
                groups.setdefault(v, []).append(k)
            text = " < ".join("=".join(sorted(groups[v])) for v in sorted(groups))
            orders.append(text + ("" if len(seen) == 3 else " (not all signals crossed)"))
            for key, col in (("latency", "onset_latency"), ("error", "onset_error"), ("timeout_log", "onset_timeout_log")):
                if pd.notna(r[col]) and pd.notna(r.onset_primary):
                    lags[key].append(r[col] - r.onset_primary)
        out[scenario] = {
            "orderings": pd.Series(orders).value_counts().to_dict(),
            "primary_onset_after_fault_min": describe(sub.onset_primary),
            "lag_after_primary_min": {k: describe(pd.Series(v, dtype=float)) for k, v in lags.items()},
        }
    return out


def describe(s):
    s = pd.Series(s, dtype=float).dropna()
    if s.empty:
        return None
    return {"min": s.min(), "max": s.max(), "mean": s.mean(), "std": s.std(), "n": int(len(s))}


def scenario_checks(signals, normals):
    """Count how many cases show each intended pattern (thresholds stated in the key)."""
    def count(sub, mask):
        return f"{int(mask.sum())}/{len(sub)}"

    db = signals[signals.scenario == DB]
    mem = signals[signals.scenario == MEM]
    dn = signals[signals.scenario == DOWN]
    return {
        DB: {
            "db util baseline <= 75% and peak >= 90%": count(db, (db.base_db_connection_utilization <= 75) & (db.peak_db_connection_utilization >= 90)),
            "latency peak >= 2x baseline": count(db, db.latency_ratio >= 2),
            "error rate rises >= 1 pp": count(db, db.error_delta >= 1),
            "timeout-related WARN/ERROR rate higher than baseline": count(db, db.timeout_per_min_incident > db.timeout_per_min_baseline),
            "CPU ratio smaller than DB-util ratio and latency ratio": count(db, (db.cpu_ratio < db.db_ratio) & (db.cpu_ratio < db.latency_ratio)),
            "CPU peak/baseline >= 2 (CPU strongly elevated)": count(db, db.cpu_ratio >= 2),
            "memory change within +/-5 pp": count(db, (db.peak_memory_usage - db.base_memory_usage).abs() <= 5),
        },
        MEM: {
            "memory rises >= 15 pp": count(mem, mem.mem_rise >= 15),
            "leak phase linear-fit R^2 >= 0.9 (gradual trend)": count(mem, mem.leak_linear_r2 >= 0.9),
            "largest 1-min step < 10% of total rise (no single jump)": count(mem, mem.leak_max_step_share < 0.1),
            "latency peak >= 1.5x baseline": count(mem, mem.latency_ratio >= 1.5),
            "Spearman(memory, latency) >= 0.5 during fault..end": count(mem, mem.spearman_mem_latency >= 0.5),
            "error rate rises >= 1 pp": count(mem, mem.error_delta >= 1),
            "error onset after memory onset": count(mem, mem.onset_error > mem.onset_primary),
            "db util peak < 60%": count(mem, mem.peak_db_connection_utilization < 60),
        },
        DOWN: {
            "reported service downstream p95 >= 2.5x baseline": count(dn, dn.reported_ds_ratio >= 2.5),
            "timeout-related WARN/ERROR rate higher than baseline": count(dn, dn.timeout_per_min_incident > dn.timeout_per_min_baseline),
            "reported service error rate rises >= 1 pp": count(dn, dn.reported_error_delta >= 1),
            "focus CPU peak/baseline < 1.3": count(dn, dn.cpu_ratio < 1.3),
            "focus memory change < 5 pp": count(dn, (dn.peak_memory_usage - dn.base_memory_usage) < 5),
            "focus db util peak < 90% (no pool saturation)": count(dn, dn.peak_db_connection_utilization.fillna(0) < 90),
        },
        NORMAL: {
            "no service with error rate > 2% for >= 1 min": count(normals, normals.longest_run_error_gt2pct_min == 0),
            "no DB utilization >= 90%": count(normals, normals.max_db_util_any < 90),
            "WARN logs present": count(normals, normals.warn_logs > 0),
            "latency fluctuates (CV > 0.05 on alerting service)": count(normals, normals.focus_latency_cv > 0.05),
        },
    }


def metadata_shortcuts(incidents, signals):
    """How far metadata fields alone separate scenarios (ranges per scenario)."""
    out = {}
    for col in ("duration_min", "window_min", "minutes_before_start_in_window"):
        out[col] = {s: describe(signals.loc[signals.scenario == s, col]) for s in SCENARIOS}
    out["severity_by_scenario"] = {s: incidents.loc[incidents.scenario == s, "severity"].value_counts().to_dict()
                                   for s in SCENARIOS}
    return out


def variation_summary(incidents, signals):
    out = {}
    for scenario in SCENARIOS:
        sub, sig = incidents[incidents.scenario == scenario], signals[signals.scenario == scenario]
        d = {
            "start_dates": [str(sub.start_time.min().date()), str(sub.start_time.max().date())],
            "unique_start_times": int(sub.start_time.nunique()),
            "start_hours": sorted(int(h) for h in sub.start_time.dt.hour.unique()),
            "severity": sub.severity.value_counts().to_dict(),
            "reported_service": sub.service.value_counts().to_dict(),
            "root_cause_service": sub.root_cause_service.value_counts().to_dict(),
            "variant": sub.root_cause_variant.value_counts().to_dict(),
        }
        for col in ("duration_min", "window_min", "fault_offset_min", "alert_lag_min", "base_cpu_usage",
                    "base_memory_usage", "base_request_rate", "base_latency_ms", "latency_ratio", "error_delta",
                    "peak_latency_ms", "peak_error_rate", "log_records"):
            s = sig[col].astype(float)
            d[col] = {"min": s.min(), "max": s.max(), "mean": s.mean(), "std": s.std(),
                      "cv": s.std() / s.mean() if s.mean() else np.nan}
        out[scenario] = d
    return out


# --------------------------------------------------------------------------- figures

PANEL_METRICS = [("db_connection_utilization", "DB connection utilization (%)", False),
                 ("memory_usage", "memory usage (%)", False), ("cpu_usage", "CPU usage (%)", False),
                 ("latency_ms", "p95 latency (ms, log)", True), ("downstream_latency_ms", "downstream p95 (ms, log)", True),
                 ("error_rate", "error rate (%)", False)]


def plot_scenario(incidents, cases, scenario, path, before=60, after=60):
    fig, axes = plt.subplots(2, 3, figsize=(14, 7), sharex=True)
    ids = incidents.index[incidents.scenario == scenario]
    colors = plt.cm.tab10(np.linspace(0, 1, len(ids)))
    for iid, color in zip(ids, colors):
        c = cases[iid]
        s = c.series(c.meta.focus)
        x = (s.index - c.meta.start_time) / MIN
        keep = (x >= -before) & (x <= after)
        for ax, (col, label, log) in zip(axes.flat, PANEL_METRICS):
            if s[col].notna().any():
                ax.plot(x[keep], s[col][keep], color=color, lw=1, alpha=0.85, label=f"{iid} {c.meta.focus}")
    for ax, (col, label, log) in zip(axes.flat, PANEL_METRICS):
        ax.set_title(label, fontsize=10)
        ax.axvline(0, color="k", ls="--", lw=0.8)
        if log:
            ax.set_yscale("log")
        ax.grid(alpha=0.3)
    for ax in axes[1]:
        ax.set_xlabel("minutes relative to incident start_time")
    handles, labels = axes.flat[3].get_legend_handles_labels()
    fig.legend(handles, labels, loc="center right", fontsize=7, frameon=False)
    who = "root-cause service" if scenario in (DB, MEM) else "reported (alerting) service"
    fig.suptitle(f"{SHORT[scenario]}: {who} of each case, aligned on start_time (dashed line)", fontsize=12)
    fig.tight_layout(rect=(0, 0, 0.86, 0.96))
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_timeline(incidents, cases, iid, path):
    c = cases[iid]
    meta, f = c.meta, c.meta.focus
    ws = meta.window_start
    rel = lambda ts: (ts - ws) / MIN
    fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
    s = c.series(f)
    x = rel(s.index)
    axes[0].plot(x, s.db_connection_utilization, label=f"{f} DB connection utilization (%)")
    axes[0].plot(x, s.cpu_usage, label=f"{f} CPU (%)")
    axes[0].plot(x, s["memory_usage"], label=f"{f} memory (%)")
    axes[0].plot(x, c.series("database").cpu_usage, label="database CPU (%)", ls=":")
    axes[0].set_ylim(0, 105)
    for svc in (f, "orders-api", "api-gateway"):
        ss = c.series(svc)
        axes[1].plot(rel(ss.index), ss.latency_ms, label=f"{svc} p95 latency")
        axes[2].plot(rel(ss.index), ss.error_rate, label=f"{svc} error rate")
    axes[1].set_yscale("log")
    axes[1].set_ylabel("ms (log)")
    axes[2].set_ylabel("%")
    per_min = c.logs.assign(minute=((c.logs.timestamp - ws) / MIN).astype(int))
    counts = per_min.groupby(["minute", "level"]).size().unstack(fill_value=0).reindex(columns=LEVELS, fill_value=0)
    bottom = np.zeros(len(counts))
    for lv, color in zip(LEVELS, ("#9ecae1", "#fdae6b", "#de2d26")):
        axes[3].bar(counts.index, counts[lv], bottom=bottom, width=1.0, color=color, label=lv)
        bottom += counts[lv].values
    timeouts = per_min[per_min.is_timeout].groupby("minute").size()
    axes[3].plot(timeouts.index, timeouts.values, color="k", lw=1, label="timeout-related messages")
    axes[3].set_ylabel("log records / min")
    deploys = c.logs[(c.logs.logger == "deploy") & (c.logs.message.str.contains("started"))]
    for ax in axes:
        ax.axvline(rel(meta.fault_start_time), color="purple", ls="--", lw=1)
        ax.axvspan(rel(meta.start_time), rel(meta.end_time), color="red", alpha=0.07)
        for t in deploys.timestamp:
            ax.axvline(rel(t), color="green", ls=":", lw=1)
        ax.legend(fontsize=7, loc="upper left")
        ax.grid(alpha=0.3)
    axes[3].set_xlabel("minutes since window_start")
    axes[0].set_title(f"{iid} ({meta.scenario}, variant={meta.root_cause_variant}, severity={meta.severity}) - "
                      "purple: fault start, red band: incident window, green: deployments", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_normal_vs_failure(cases, normal_id, failure_id, path):
    fig, axes = plt.subplots(4, 2, figsize=(13, 10), sharey="row")
    for col_idx, iid in enumerate((normal_id, failure_id)):
        c = cases[iid]
        s = c.series(c.meta.service)
        x = (s.index - c.meta.start_time) / MIN
        rows = [("latency_ms", "p95 latency (ms)"), ("error_rate", "error rate (%)"),
                ("db_connection_utilization", "DB conn. utilization (%)")]
        for row_idx, (col, label) in enumerate(rows):
            ax = axes[row_idx, col_idx]
            ax.plot(x, s[col], lw=1)
            ax.axvspan(0, (c.meta.end_time - c.meta.start_time) / MIN, color="red", alpha=0.08)
            ax.set_ylabel(label)
            ax.grid(alpha=0.3)
        per_min = c.logs.assign(minute=((c.logs.timestamp - c.meta.start_time) / MIN).floordiv(1))
        for lv, color in (("WARN", "#fdae6b"), ("ERROR", "#de2d26")):
            cnt = per_min[per_min.level == lv].groupby("minute").size()
            axes[3, col_idx].plot(cnt.index, cnt.values, color=color, lw=1, label=lv)
        axes[3, col_idx].set_ylabel("log records / min (all services)")
        axes[3, col_idx].set_xlabel("minutes relative to start_time (red band: investigation window)")
        axes[3, col_idx].legend(fontsize=8)
        axes[3, col_idx].grid(alpha=0.3)
        axes[0, col_idx].set_title(f"{iid}: {c.meta.scenario} on {c.meta.service} ({c.meta.severity})", fontsize=10)
    axes[0, 0].set_yscale("log")
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def plot_separation(signals, path):
    features = [("peak_db_connection_utilization", "focus: peak DB util (%)"),
                ("mem_rise", "focus: memory rise (pp)"),
                ("reported_ds_ratio", "reported svc: downstream p95 ratio"),
                ("latency_ratio", "focus: latency peak/baseline"),
                ("error_delta", "focus: error rate rise (pp)"),
                ("cpu_ratio", "focus: CPU peak/baseline")]
    fig, axes = plt.subplots(1, len(features), figsize=(18, 4.2))
    rng = np.random.default_rng(0)
    for ax, (col, label) in zip(axes, features):
        for i, s in enumerate(SCENARIOS):
            vals = signals.loc[signals.scenario == s, col].dropna().astype(float)
            ax.scatter(i + rng.uniform(-0.15, 0.15, len(vals)), vals, s=18, alpha=0.8)
        ax.set_xticks(range(len(SCENARIOS)), [SHORT[s].replace(" ", "\n") for s in SCENARIOS], fontsize=8)
        ax.set_title(label, fontsize=9)
        if col in ("reported_ds_ratio", "latency_ratio"):
            ax.set_yscale("log")
        ax.grid(alpha=0.3)
    fig.suptitle("Per-case signal strength (incident window vs 30-min pre-fault baseline); one dot per case", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


# --------------------------------------------------------------------------- output helpers

def fmt(v, digits=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "-"
    return f"{v:,.{digits}f}"


def md_table(df, digits=1):
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(fmt(v, digits) if isinstance(v, (float, np.floating)) else str(v)
                                        for v in r.values) + " |")
    return "\n".join(lines)


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return None if np.isnan(obj) else round(float(obj), 4)
    return obj


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    incidents, metrics, logs = load()
    cases = {iid: Case(meta, metrics[metrics.incident_id == iid], logs[logs.incident_id == iid])
             for iid, meta in incidents.iterrows()}

    summary = dataset_summary(incidents, metrics, logs)
    stats = metric_stats(incidents, cases)
    stats_all = metric_stats_all_rows(incidents, metrics)
    signals = incident_signals(incidents, cases)
    normals = normal_checks(incidents, cases)
    templates, keywords = template_analysis(incidents, logs)
    leakage = leakage_checks(incidents, metrics, logs)
    ordering = ordering_analysis(signals)
    variation = variation_summary(incidents, signals)
    checks = scenario_checks(signals, normals)
    shortcuts = metadata_shortcuts(incidents, signals)

    stats.to_csv(RES / "metric_stats_focus_service.csv", index=False)
    stats_all.to_csv(RES / "metric_stats_all_rows.csv")
    signals.to_csv(RES / "incident_signals.csv", index=False)
    normals.to_csv(RES / "normal_cases.csv", index=False)
    keywords.to_csv(RES / "keyword_presence.csv", index=False)
    (RES / "summary.json").write_text(json.dumps(jsonable({
        "dataset": summary, "checks": checks, "templates": templates, "leakage": leakage,
        "ordering": ordering, "metadata_shortcuts": shortcuts, "variation": variation}), indent=2), encoding="utf-8")

    # figures
    plot_scenario(incidents, cases, DB, FIG / "scenario_db_pool_exhaustion.png")
    plot_scenario(incidents, cases, MEM, FIG / "scenario_memory_leak.png", before=150)
    plot_scenario(incidents, cases, DOWN, FIG / "scenario_downstream_timeout.png")
    plot_scenario(incidents, cases, NORMAL, FIG / "scenario_normal.png")
    db_ids = signals[(signals.scenario == DB) & (signals.variant == "connection_leak")].index
    timeline_id = "INC-011" if "INC-011" in db_ids else db_ids[0]
    plot_timeline(incidents, cases, timeline_id, FIG / f"timeline_{timeline_id}.png")
    normal_id = incidents.index[(incidents.scenario == NORMAL)][0]
    same_svc = signals[(signals.scenario == DB) & (signals.service == incidents.loc[normal_id, "service"])]
    failure_id = same_svc.index[0] if len(same_svc) else signals[signals.scenario == DB].index[0]
    plot_normal_vs_failure(cases, normal_id, failure_id, FIG / f"normal_vs_failure_{normal_id}_{failure_id}.png")
    plot_separation(signals, FIG / "signal_separation.png")

    # markdown tables for the report
    md = []
    for scenario in SCENARIOS:
        sub = stats[stats.scenario == scenario]
        rows = []
        for col in METRICS:
            b = sub[(sub.phase == "baseline") & (sub.metric == col)].iloc[0]
            i = sub[(sub.phase == "incident") & (sub.metric == col)].iloc[0]
            if b.n == 0:
                continue
            rows.append({"metric": col, "baseline mean": b["mean"], "baseline std": b["std"],
                         "baseline min-max": f"{fmt(b['min'])}-{fmt(b['max'])}",
                         "incident mean": i["mean"], "incident std": i["std"],
                         "incident min-max": f"{fmt(i['min'])}-{fmt(i['max'])}"})
        md.append(f"### {scenario}\n\n{md_table(pd.DataFrame(rows))}\n")
    sig_cols = {DB: ["incident_id", "variant", "focus", "severity", "base_db_connection_utilization",
                     "peak_db_connection_utilization", "latency_ratio", "error_delta", "cpu_ratio",
                     "timeout_per_min_baseline", "timeout_per_min_incident"],
                MEM: ["incident_id", "variant", "focus", "severity", "base_memory_usage", "mem_rise",
                      "leak_minutes_to_peak", "leak_linear_r2", "leak_max_step_share", "spearman_mem_latency",
                      "latency_ratio", "error_delta", "cpu_ratio", "oom_events"],
                DOWN: ["incident_id", "variant", "service", "root", "severity", "reported_ds_ratio",
                       "reported_latency_ratio", "reported_error_delta", "timeout_per_min_baseline",
                       "timeout_per_min_incident", "cpu_ratio", "mem_delta"]}
    signals["root"] = incidents.root_cause_service
    signals["mem_delta"] = signals.peak_memory_usage - signals.base_memory_usage
    for scenario, cols in sig_cols.items():
        md.append(f"### Signals: {scenario}\n\n{md_table(signals.loc[signals.scenario == scenario, cols], 2)}\n")
    md.append(f"### NORMAL cases\n\n{md_table(normals, 2)}\n")
    md.append(f"### Keyword presence (share of cases with >=1 WARN/ERROR match)\n\n{md_table(keywords, 2)}\n")
    (RES / "tables.md").write_text("\n".join(md), encoding="utf-8")

    print(f"cases={summary['total_cases']} logs={summary['log_records']} metric_rows={summary['metric_rows']}")
    print(f"figures -> {FIG.relative_to(ROOT)}; results -> {RES.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
