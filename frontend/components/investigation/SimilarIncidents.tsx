"use client";

import { useState } from "react";
import type { HistoricalCardModel } from "@/lib/types";

export function SimilarIncidents({ items }: { items: HistoricalCardModel[] }) {
  const [openId, setOpenId] = useState<string | null>(null);
  return (
    <section className="panel" aria-labelledby="similar-heading" data-testid="similar">
      <h2 id="similar-heading">Similar incidents</h2>
      <p className="lede">
        Historical references. A similar past incident is not evidence that this incident has the same cause.
      </p>
      {items.length === 0 ? (
        <p className="empty">No historical incident was retrieved.</p>
      ) : (
        <div className="stack">
          {items.map((item) => {
            const open = openId === item.incident_id;
            return (
              <article key={item.incident_id} className="subcard">
                <h3 className="mono">{item.incident_id}</h3>
                <p>{item.incident_type}</p>
                <p>{item.similarity_note}</p>
                <button
                  type="button"
                  className="ghost"
                  aria-expanded={open}
                  onClick={() => setOpenId(open ? null : item.incident_id)}
                >
                  {open ? "Hide historical detail" : "Show historical detail"}
                </button>
                {open ? (
                  <div>
                    {item.symptoms ? (
                      <p>
                        <strong>Observed symptoms. </strong>
                        {item.symptoms}
                      </p>
                    ) : null}
                    {item.resolution_summary ? (
                      <p>
                        <strong>Resolution summary. </strong>
                        {item.resolution_summary}
                      </p>
                    ) : (
                      <p>No resolution summary was included beyond the similarity note.</p>
                    )}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
