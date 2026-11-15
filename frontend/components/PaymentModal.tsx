"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Spinner } from "@/components/ui";
import type { PaymentDetails } from "@/hooks/useVoiceCall";
import { formatClock, formatDay, formatFee } from "@/lib/format";

type Phase = "review" | "processing" | "success";

const PROCESSING_MS = 1600;
const SUCCESS_MS = 900;

type Props = {
  details: PaymentDetails;
  onDone: (paid: boolean) => void;
};

export default function PaymentModal({ details, onDone }: Props) {
  const [phase, setPhase] = useState<Phase>("review");
  const payButton = useRef<HTMLButtonElement>(null);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    payButton.current?.focus();
    const pending = timers.current;
    return () => pending.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && phase === "review") onDone(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, onDone]);

  function pay() {
    setPhase("processing");
    timers.current.push(
      setTimeout(() => {
        setPhase("success");
        timers.current.push(setTimeout(() => onDone(true), SUCCESS_MS));
      }, PROCESSING_MS),
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="payment-title"
        className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-xl"
      >
        {phase === "success" ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center" role="status">
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-teal-100 text-teal-700">
              <svg viewBox="0 0 24 24" className="h-7 w-7" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M5 12l5 5 9-10" />
              </svg>
            </span>
            <p className="text-lg font-semibold text-slate-900">Payment successful</p>
            <p className="text-sm text-slate-500">Finishing your booking…</p>
          </div>
        ) : (
          <>
            <h2 id="payment-title" className="text-lg font-semibold text-slate-900">
              Complete your payment
            </h2>
            <p className="mt-1 text-sm text-slate-500">Your appointment is booked once this is paid.</p>

            <dl className="mt-4 space-y-2 rounded-xl bg-slate-50 p-4 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">Doctor</dt>
                <dd className="text-right font-medium text-slate-900">
                  {details.doctor}
                  {details.specialty && <span className="block text-xs font-normal text-slate-500">{details.specialty}</span>}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-slate-500">When</dt>
                <dd className="text-right font-medium text-slate-900">
                  {formatDay(details.date)}
                  <span className="block text-xs font-normal text-slate-500">{formatClock(details.time)}</span>
                </dd>
              </div>
              <div className="flex items-baseline justify-between gap-4 border-t border-slate-200 pt-2">
                <dt className="text-slate-500">Amount</dt>
                <dd className="text-xl font-semibold text-slate-900">{formatFee(details.amount, details.currency)}</dd>
              </div>
            </dl>

            <p className="mt-3 text-xs text-slate-500">This is a demo payment. No money is charged.</p>

            <div className="mt-5 flex flex-col gap-2">
              <Button ref={payButton as never} onClick={pay} disabled={phase === "processing"}>
                {phase === "processing" ? (
                  <>
                    <Spinner /> Processing…
                  </>
                ) : (
                  `Pay ${formatFee(details.amount, details.currency)}`
                )}
              </Button>
              <Button variant="secondary" onClick={() => onDone(false)} disabled={phase === "processing"}>
                Cancel
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}