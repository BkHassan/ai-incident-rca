export function RCAHeader({ incidentId }: { incidentId: string }) {
  return (
    <header className="page-head">
      <p className="kicker">Investigation result</p>
      <h1 className="page-title">{incidentId}</h1>
      <p className="meta">Hypothesis, observed evidence, and recommended actions are marked separately.</p>
    </header>
  );
}
