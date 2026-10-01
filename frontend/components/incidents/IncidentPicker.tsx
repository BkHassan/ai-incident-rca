"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { incidentIdPattern } from "@/lib/product";

export function IncidentPicker({ current }: { current: string | null }) {
  const router = useRouter();
  const [value, setValue] = useState(current ?? "");
  const [error, setError] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    const next = value.trim().toUpperCase();
    if (!incidentIdPattern.test(next)) {
      setError("Use an id like INC-011. The API accepts INC- and three digits.");
      return;
    }
    setError("");
    router.push(`/incidents?incident=${next}`);
  }

  return (
    <form className="picker" onSubmit={submit}>
      <label htmlFor="incident-id">Incident id</label>
      <div className="picker-row">
        <input
          id="incident-id"
          name="incident"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          autoComplete="off"
          spellCheck={false}
          placeholder="INC-011"
        />
        <button type="submit">Select</button>
      </div>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : (
        <p className="meta">This only records the id in the console. It does not load a record or start an investigation.</p>
      )}
    </form>
  );
}
