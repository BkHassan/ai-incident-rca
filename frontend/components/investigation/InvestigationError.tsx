export function InvestigationError({ message, retryHref }: { message: string; retryHref: string }) {
  return (
    <section className="panel error-state" aria-labelledby="error-heading" data-testid="error" role="alert">
      <h1 id="error-heading">Investigation unavailable</h1>
      <p>{message}</p>
      <a className="button" href={retryHref}>
        Try again
      </a>
    </section>
  );
}
