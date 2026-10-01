const known = new Set(["CRITICAL", "HIGH", "MEDIUM", "LOW"]);

export function SeverityBadge({ severity }: { severity: string }) {
  const tone = known.has(severity) ? severity.toLowerCase() : "unknown";
  return <span className={`badge severity severity-${tone}`}>{severity}</span>;
}
