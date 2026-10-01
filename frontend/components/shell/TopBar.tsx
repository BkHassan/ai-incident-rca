"use client";

import { StatusIndicator } from "@/components/ui/StatusIndicator";
import { systemStatus } from "@/lib/product";

export function TopBar({
  section,
  incidentId,
  menuOpen,
  onMenu,
}: {
  section: string;
  incidentId: string | null;
  menuOpen: boolean;
  onMenu: () => void;
}) {
  return (
    <header className="topbar">
      <button
        type="button"
        className="menu-button"
        aria-expanded={menuOpen}
        aria-controls="primary-nav"
        onClick={onMenu}
      >
        {menuOpen ? "Close" : "Menu"}
      </button>
      <div className="topbar-section">
        <p className="kicker">Section</p>
        <p className="topbar-title">{section}</p>
      </div>
      <div className="topbar-incident">
        <p className="kicker">Selected incident</p>
        <p className="mono">{incidentId ?? "None"}</p>
      </div>
      <StatusIndicator label={systemStatus.label} detail={systemStatus.detail} tone={systemStatus.tone} />
    </header>
  );
}
