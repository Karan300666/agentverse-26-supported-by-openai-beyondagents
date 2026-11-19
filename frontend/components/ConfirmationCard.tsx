"use client";

import type { Confirmation } from "@/hooks/useVoiceCall";
import { formatClock, formatDay, formatFee } from "@/lib/format";

const TITLES = {
  booked: "Appointment booked",
  cancelled: "Appointment cancelled",
  rescheduled: "Appointment rescheduled",
} as const;

type Props = { confirmation: Confirmation; onClose: () => void };

export default function ConfirmationCard({ confirmation, onClose }: Props) {
  const { kind, doctor, specialty, date, time, feeAmount, currency } = confirmation;
  const cancelled = kind === "cancelled";

  return (
    <section
      role="status"
      aria-live="polite"
      className={`rounded-2xl border p-4 shadow-sm ${
        cancelled ? "border-slate-200 bg-white" : "border-teal-200 bg-teal-50"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
            cancelled ? "bg-slate-100 text-slate-600" : "bg-teal-600 text-white"
          }`}
        >
          <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {cancelled ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M5 12l5 5 9-10" />}
          </svg>
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-slate-900">{TITLES[kind]}</p>
          <p className="mt-0.5 text-sm text-slate-700">
            {doctor}
            {specialty && <span className="text-slate-500"> · {specialty}</span>}
          </p>
          <p className="text-sm text-slate-700">
            {formatDay(date)} at {formatClock(time)}
          </p>
          {!cancelled && feeAmount !== null && (
            <p className="text-sm text-slate-500">Fee {formatFee(feeAmount, currency)}</p>
          )}
        </div>
        <button
          type="button"
          aria-label="Dismiss"
          onClick={onClose}
          className="rounded-lg px-2 py-1 text-lg leading-none text-slate-400 hover:bg-white hover:text-slate-600"
        >
          ×
        </button>
      </div>
    </section>
  );
}