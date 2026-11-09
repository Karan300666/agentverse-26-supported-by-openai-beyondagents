"use client";

import { useState } from "react";
import { useVoiceCall } from "@/hooks/useVoiceCall";

const ROLE_STYLES = {
  patient: "bg-blue-50 text-blue-900 self-end",
  assistant: "bg-gray-100 text-gray-900 self-start",
  tool: "bg-amber-50 text-amber-900 self-center text-xs font-mono",
} as const;

export default function Home() {
  const [phone, setPhone] = useState("");
  const { status, error, transcript, connect, disconnect } = useVoiceCall();

  const phoneValid = /^\d{10}$/.test(phone);
  const inCall = status === "connecting" || status === "connected";

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col gap-4 p-6">
      <h1 className="text-2xl font-semibold">Hospital Voice Receptionist (test page)</h1>

      <div className="flex gap-2">
        <input
          className="flex-1 rounded border px-3 py-2 disabled:bg-gray-100"
          placeholder="10-digit phone number"
          inputMode="numeric"
          maxLength={10}
          value={phone}
          disabled={inCall}
          onChange={(e) => setPhone(e.target.value.replace(/\D/g, ""))}
        />
        {inCall ? (
          <button className="rounded bg-red-600 px-4 py-2 text-white" onClick={disconnect}>
            Hang up
          </button>
        ) : (
          <button
            className="rounded bg-green-600 px-4 py-2 text-white disabled:opacity-40"
            disabled={!phoneValid}
            onClick={() => connect(phone)}
          >
            Call
          </button>
        )}
      </div>

      <p className="text-sm text-gray-600">
        Status: <span className="font-medium">{status}</span>
      </p>
      {error && <p className="rounded bg-red-50 p-2 text-sm text-red-700">{error}</p>}

      <div className="flex flex-1 flex-col gap-2 rounded border p-3">
        {transcript.length === 0 && (
          <p className="text-sm text-gray-400">The conversation will appear here.</p>
        )}
        {transcript.map((line) => (
          <div
            key={line.id}
            className={`max-w-[85%] whitespace-pre-wrap break-words rounded px-3 py-2 ${ROLE_STYLES[line.role]}`}
          >
            {line.text}
          </div>
        ))}
      </div>
    </main>
  );
}