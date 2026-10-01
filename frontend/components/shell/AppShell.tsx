"use client";

import { Suspense, useState, type ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { Sidebar } from "@/components/shell/Sidebar";
import { TopBar } from "@/components/shell/TopBar";
import { navigation, parseIncidentId } from "@/lib/product";

function ShellFrame({
  children,
  pathname,
  incidentId,
  menuOpen,
  onMenu,
  onNavigate,
}: {
  children: ReactNode;
  pathname: string;
  incidentId: string | null;
  menuOpen: boolean;
  onMenu: () => void;
  onNavigate: () => void;
}) {
  const section = navigation.find((item) => item.href === pathname)?.label ?? "Incident RCA";

  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <aside id="primary-nav" className={menuOpen ? "sidebar open" : "sidebar"}>
        <Sidebar currentPath={pathname} incidentId={incidentId} onNavigate={onNavigate} />
      </aside>
      {menuOpen ? (
        <button type="button" className="backdrop" aria-label="Close menu" onClick={onMenu} />
      ) : null}
      <div className="workspace">
        <TopBar section={section} incidentId={incidentId} menuOpen={menuOpen} onMenu={onMenu} />
        <main id="main" className="main">
          {children}
        </main>
      </div>
    </>
  );
}

function ShellWithParams({
  children,
  menuOpen,
  onMenu,
  onNavigate,
}: {
  children: ReactNode;
  menuOpen: boolean;
  onMenu: () => void;
  onNavigate: () => void;
}) {
  const pathname = usePathname();
  const params = useSearchParams();
  const incidentId = parseIncidentId(params.get("incident") ?? undefined);

  return (
    <ShellFrame
      pathname={pathname}
      incidentId={incidentId}
      menuOpen={menuOpen}
      onMenu={onMenu}
      onNavigate={onNavigate}
    >
      {children}
    </ShellFrame>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const close = () => setMenuOpen(false);
  const toggle = () => setMenuOpen((open) => !open);

  return (
    <div className="app">
      <Suspense
        fallback={
          <ShellFrame
            pathname={pathname}
            incidentId={null}
            menuOpen={menuOpen}
            onMenu={toggle}
            onNavigate={close}
          >
            {children}
          </ShellFrame>
        }
      >
        <ShellWithParams menuOpen={menuOpen} onMenu={toggle} onNavigate={close}>
          {children}
        </ShellWithParams>
      </Suspense>
    </div>
  );
}
