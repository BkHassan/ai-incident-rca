"use client";

import { useState } from "react";
import type { TechnicalCardModel } from "@/lib/types";

export function TechnicalEvidence({ items }: { items: TechnicalCardModel[] }) {
  const [openId, setOpenId] = useState<string | null>(items[0]?.document_id ?? null);
  return (
    <section className="panel" aria-labelledby="technical-heading" data-testid="technical">
      <h2 id="technical-heading">Technical evidence</h2>
      <p className="lede">Retrieved documentation. It explains mechanisms. It is not an observation from this incident.</p>
      {items.length === 0 ? (
        <p className="empty">No technical document was retrieved.</p>
      ) : (
        <div className="stack">
          {items.map((item) => {
            const open = openId === item.document_id;
            return (
              <article key={item.document_id} className="subcard">
                <h3>{item.title}</h3>
                {item.section ? <p>{item.section}</p> : null}
                <p className="event-meta">
                  <span className="mono">{item.document_id}</span>
                  {item.source_path ? <span className="mono">{item.source_path}</span> : null}
                </p>
                <button
                  type="button"
                  className="ghost"
                  aria-expanded={open}
                  onClick={() => setOpenId(open ? null : item.document_id)}
                >
                  {open ? "Hide excerpt" : "Show excerpt"}
                </button>
                {open ? <blockquote>{item.excerpt}</blockquote> : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
