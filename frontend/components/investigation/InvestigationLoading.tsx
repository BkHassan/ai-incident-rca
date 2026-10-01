const STEPS = [
  { label: "Loading incident telemetry", state: "done" },
  { label: "Detecting anomalies", state: "done" },
  { label: "Correlating timeline", state: "done" },
  { label: "Retrieving similar incidents", state: "current" },
  { label: "Generating RCA", state: "waiting" },
] as const;

export function InvestigationLoading({ fixtureMode }: { fixtureMode: boolean }) {
  return (
    <section className="panel loading" aria-labelledby="loading-heading" data-testid="loading" aria-busy="true">
      <h1 id="loading-heading">Analyzing incident</h1>
      <ol>
        {STEPS.map((step) => (
          <li key={step.label} data-state={step.state}>
            <span className="step-state">
              {step.state === "done" ? "Done" : step.state === "current" ? "In progress" : "Waiting"}
            </span>
            {step.label}
          </li>
        ))}
      </ol>
      {fixtureMode ? (
        <p role="note">Demo preview. These steps are not running against Gemini or Chroma.</p>
      ) : (
        <p>Waiting for the investigation service.</p>
      )}
    </section>
  );
}
