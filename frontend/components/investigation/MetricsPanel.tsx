import type { MetricSeriesModel } from "@/lib/types";

export function MetricsPanel({ series, demo }: { series: MetricSeriesModel[]; demo: boolean }) {
  return (
    <section className="panel" aria-labelledby="metrics-heading" data-testid="metrics">
      <h2 id="metrics-heading">Metrics</h2>
      <p className="lede">
        {demo
          ? "Illustrative series for this demo. Not live telemetry. The shaded band marks the change after baseline."
          : series.length
            ? "Series attached to this investigation."
            : "Metric series are not part of the RCA response. They are shown when the demo fixture supplies them."}
      </p>
      {series.length === 0 ? (
        <p className="empty">No metric series to chart.</p>
      ) : (
        <div className="metric-grid">
          {series.map((item) => (
            <MetricChart key={item.id} series={item} />
          ))}
        </div>
      )}
    </section>
  );
}

function MetricChart({ series }: { series: MetricSeriesModel }) {
  const width = 320;
  const height = 96;
  const pad = 10;
  const values = series.points;
  const min = Math.min(...values, series.baseline);
  const max = Math.max(...values, series.baseline);
  const span = max - min || 1;
  const x = (index: number) => pad + (index / Math.max(values.length - 1, 1)) * (width - pad * 2);
  const y = (value: number) => height - pad - ((value - min) / span) * (height - pad * 2);
  const path = values.map((value, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
  const from = series.anomalyFrom;
  const to = series.anomalyTo;
  const band =
    from !== null && to !== null
      ? { x: x(from), width: Math.max(x(to) - x(from), 2) }
      : null;

  return (
    <figure className="metric">
      <figcaption>
        <span>{series.label}</span>
        <span className="mono">
          {values[values.length - 1]}
          {series.unit}
        </span>
      </figcaption>
      <svg role="img" viewBox={`0 0 ${width} ${height}`} aria-label={series.summary}>
        <title>{series.summary}</title>
        {band ? <rect className="band" x={band.x} y={pad} width={band.width} height={height - pad * 2} /> : null}
        <line className="baseline" x1={pad} x2={width - pad} y1={y(series.baseline)} y2={y(series.baseline)} />
        <path d={path} />
      </svg>
      <p>{series.summary}</p>
    </figure>
  );
}
