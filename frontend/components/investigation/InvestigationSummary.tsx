export function InvestigationSummary({ summary }: { summary: string }) {
  return (
    <section className="panel" aria-labelledby="summary-heading" data-testid="summary">
      <h2 id="summary-heading">Investigation summary</h2>
      <p>{summary}</p>
    </section>
  );
}
