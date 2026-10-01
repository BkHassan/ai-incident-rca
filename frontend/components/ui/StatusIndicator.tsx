export function StatusIndicator({
  label,
  detail,
  tone = "attention",
}: {
  label: string;
  detail: string;
  tone?: "attention" | "neutral";
}) {
  return (
    <p className={`status status-${tone}`} role="status">
      <span className="status-mark" aria-hidden="true" />
      <span>
        <strong>{label}</strong>
        <span className="status-detail">{detail}</span>
      </span>
    </p>
  );
}
