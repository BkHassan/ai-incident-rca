import type { ReactNode } from "react";

export function StatePanel({
  title,
  happened,
  next,
  actions,
  alert = false,
}: {
  title: string;
  happened: string;
  next: string;
  actions?: ReactNode;
  alert?: boolean;
}) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      <p {...(alert ? { role: "alert" } : {})}>{happened}</p>
      <p className="meta">Next: {next}</p>
      {actions ? <div className="action-row">{actions}</div> : null}
    </div>
  );
}
