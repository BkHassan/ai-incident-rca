import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-sans",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
});

export const metadata: Metadata = {
  title: "Incident investigation",
  description: "Investigation view for one software incident.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${sans.variable} ${mono.variable}`}>
        <a className="skip" href="#investigation">
          Skip to investigation
        </a>
        <div className="appbar">
          <strong>Incident RCA</strong>
          <span>Investigation</span>
        </div>
        <div className="shell" id="investigation">
          {children}
        </div>
      </body>
    </html>
  );
}
