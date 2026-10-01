"use client";

import { useState } from "react";

export function CopyId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button type="button" className="text-button" onClick={() => void copy()} aria-label={`Copy evidence id ${id}`}>
      {copied ? "Copied" : "Copy id"}
    </button>
  );
}
