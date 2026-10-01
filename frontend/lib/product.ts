/** Product copy and navigation. Strings live here so pages do not repeat them. */

export const product = {
  name: "Incident RCA",
  mark: "RCA",
  tagline: "Incident intelligence",
} as const;

export const systemStatus = {
  label: "Result path blocked",
  detail:
    "Documented state, not a live probe. There is no health endpoint. A successful investigation needs the Chroma store and Gemini access.",
  tone: "attention",
} as const;

export const navigation = [
  {
    href: "/",
    label: "Overview",
    description: "How to enter the console",
  },
  {
    href: "/incidents",
    label: "Incidents",
    description: "Browse the incident catalog",
  },
  {
    href: "/investigations",
    label: "Investigations",
    description: "Investigation result, not built in this step",
  },
  {
    href: "/knowledge",
    label: "Knowledge",
    description: "Retrieval collections, no list API",
  },
] as const;

export type NavHref = (typeof navigation)[number]["href"];

export const incidentIdPattern = /^INC-\d{3}$/;

export function parseIncidentId(value: string | undefined): string | null {
  if (!value || !incidentIdPattern.test(value)) return null;
  return value;
}

export function hrefWithIncident(href: string, incidentId: string | null): string {
  if (!incidentId) return href;
  return `${href}?incident=${incidentId}`;
}

export function incidentIdFromPath(pathname: string): string | null {
  const match = /^\/incidents\/(INC-\d{3})$/.exec(pathname);
  return match?.[1] ?? null;
}

export function isNavActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function sectionForPath(pathname: string): string {
  const match = navigation.find((item) => isNavActive(pathname, item.href));
  return match?.label ?? product.name;
}

export const catalogNote = "Catalog: GET /api/incidents";
