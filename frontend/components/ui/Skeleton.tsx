export function Skeleton({ label, lines = 4 }: { label: string; lines?: number }) {
  return (
    <div className="skeleton" role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, index) => (
        <span key={index} className="skeleton-line" style={{ width: `${88 - (index % 3) * 12}%` }} />
      ))}
    </div>
  );
}
