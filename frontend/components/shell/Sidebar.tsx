"use client";

import Link from "next/link";
import { hrefWithIncident, navigation, product } from "@/lib/product";

export function Sidebar({
  currentPath,
  incidentId,
  onNavigate,
}: {
  currentPath: string;
  incidentId: string | null;
  onNavigate?: () => void;
}) {
  return (
    <div className="sidebar-inner">
      <Link className="brand" href={hrefWithIncident("/", incidentId)} onClick={onNavigate}>
        <span className="brand-mark">{product.mark}</span>
        <span>
          <span className="brand-name">{product.name}</span>
          <span className="brand-tag">{product.tagline}</span>
        </span>
      </Link>
      <nav aria-label="Primary">
        <ul className="nav-list">
          {navigation.map((item) => {
            const active = currentPath === item.href;
            return (
              <li key={item.href}>
                <Link
                  href={hrefWithIncident(item.href, incidentId)}
                  aria-current={active ? "page" : undefined}
                  onClick={onNavigate}
                >
                  <span>{item.label}</span>
                  <span className="nav-note">{item.description}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <p className="sidebar-foot">One HTTP route: POST /api/incidents/investigate</p>
    </div>
  );
}
