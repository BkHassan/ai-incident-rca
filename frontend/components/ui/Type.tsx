import type { ReactNode } from "react";

export function Kicker({ children }: { children: ReactNode }) {
  return <p className="kicker">{children}</p>;
}

export function PageTitle({ children }: { children: ReactNode }) {
  return <h1 className="page-title">{children}</h1>;
}

export function SectionTitle({ id, children }: { id: string; children: ReactNode }) {
  return (
    <h2 id={id} className="section-title">
      {children}
    </h2>
  );
}

export function Body({ children }: { children: ReactNode }) {
  return <p className="body">{children}</p>;
}

export function Meta({ children }: { children: ReactNode }) {
  return <p className="meta">{children}</p>;
}
