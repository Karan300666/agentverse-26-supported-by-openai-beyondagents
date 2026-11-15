"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import PaymentModal from "@/components/PaymentModal";
import {
  Alert,
  BrandMark,
  Button,
  CaptionsIcon,
  MicIcon,
  MicOffIcon,
  Spinner,
} from "@/components/ui";
import { useVoiceCall, type PaymentDetails } from "@/hooks/useVoiceCall";
import type { Patient } from "@/lib/api";
import { formatDuration } from "@/lib/format";

const SHOW_TOOL_DEBUG = process.env.NEXT_PUBLIC_SHOW_TOOL_DEBUG === "true";

const EXAMPLES = [
  "I'd like to book a cardiologist for tomorrow.",
  "Is Dr. Mehta free on Wednesday?",
  "What appointments do I have?",
  "Please cancel my appointment.",
];

const BUBBLE = {
  patient: "self-end bg-teal-600 text-white",
  assistant: "self-start border border-slate-200 bg-white text-slate-900",
  tool: "self-center bg-amber-50 font-mono text-xs text-amber-900",
} as const;

type PaymentRequest = { details: PaymentDetails; resolve: (paid: boolean) => void };

type Props = { patient: Patient; onLogout: () => void };

export default function VoiceCall({ patient, onLogout }: Props) {
  const [payment, setPayment] = useState<PaymentRequest | null>(null);
  const paymentRef = useRef<PaymentRequest | null>(null);
  const [showCaptions, setShowCaptions] = useState(true);

  const requestPayment = useCallback(
    (details: PaymentDetails) =>
      new Promise<boolean>((resolve) => {
        const request = { details, resolve };
        paymentRef.current = request;
        setPayment(request);
      }),
    [],
  );

  const finishPayment = useCallback((paid: boolean) => {
    const current = paymentRef.current;
    paymentRef.current = null;
    setPayment(null);
    current?.resolve(paid);
  }, []);

  const { status, error, transcript, muted, connectedAt, pendingTools, connect, disconnect, toggleMute } =
    useVoiceCall({ requestPayment });

  const inCall = status === "connecting" || status === "connected";

  // If the call ends while the payment screen is open, close it as cancelled.
  useEffect(() => {
    if (status === "idle" || status === "error") finishPayment(false);
  }, [status, finishPayment]);

  // Elapsed time
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!connectedAt) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [connectedAt]);
  const elapsed = connectedAt ? Math.max(0, Math.floor((now - connectedAt) / 1000)) : 0;

  // Keep the newest message in view
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [transcript, showCaptions]);

  async function handleLogout() {
    await disconnect(); // end any call first so the session slot is freed
    onLogout();
  }

  const statusText =
    status === "connecting"
      ? "Connecting…"
      : status === "connected"
        ? pendingTools > 0
          ? "Checking details…"
          : muted
            ? "Microphone muted"
            : "Connected"
        : status === "error"
          ? "Couldn't connect"
          : "Not connected";

  const visible = transcript.filter((line) => SHOW_TOOL_DEBUG || line.role !== "tool");

  return (
    <div className="min-h-screen bg-gradient-to-b from-sky-50 to-white">
      <header className="border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
          <BrandMark />
          <div className="flex items-center gap-3">
            <span className="hidden text-sm text-slate-600 sm:inline">{patient.name}</span>
            <Button variant="secondary" className="!py-1.5" onClick={handleLogout}>
              Log out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-5xl gap-6 px-4 py-6 md:grid-cols-[320px_1fr]">
        {/* Call card */}
        <section className="flex flex-col items-center gap-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="self-start text-lg font-semibold text-slate-900">Hello, {patient.name.split(" ")[0]}</h1>

          <div className="relative flex h-28 w-28 items-center justify-center">
            {status === "connected" && !muted && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-teal-300 opacity-30" />
            )}
            <span
              className={`relative flex h-24 w-24 items-center justify-center rounded-full ${
                status === "connected"
                  ? "bg-teal-600 text-white"
                  : status === "connecting"
                    ? "bg-sky-100 text-sky-700"
                    : "bg-slate-100 text-slate-500"
              }`}
            >
              {status === "connecting" ? (
                <Spinner className="h-8 w-8" />
              ) : muted ? (
                <MicOffIcon className="h-9 w-9" />
              ) : (
                <MicIcon className="h-9 w-9" />
              )}
            </span>
          </div>

          <div className="text-center" aria-live="polite">
            <p className="text-sm font-medium text-slate-900">{statusText}</p>
            <p className="mt-0.5 font-mono text-2xl tabular-nums text-slate-700">
              {status === "connected" ? formatDuration(elapsed) : "00:00"}
            </p>
          </div>

          {inCall ? (
            <Button variant="danger" className="w-full" onClick={() => void disconnect()}>
              End call
            </Button>
          ) : (
            <Button className="w-full" onClick={() => void connect(patient.phone)}>
              Start call
            </Button>
          )}

          <div className="grid w-full grid-cols-2 gap-2">
            <Button
              variant="secondary"
              aria-pressed={muted}
              disabled={status !== "connected"}
              onClick={toggleMute}
            >
              {muted ? <MicOffIcon className="h-4 w-4" /> : <MicIcon className="h-4 w-4" />}
              {muted ? "Unmute" : "Mute"}
            </Button>
            <Button
              variant="secondary"
              aria-pressed={showCaptions}
              onClick={() => setShowCaptions((v) => !v)}
            >
              <CaptionsIcon className="h-4 w-4" />
              Captions {showCaptions ? "on" : "off"}
            </Button>
          </div>

          {error && (
            <div className="w-full">
              <Alert>
                {error === "Unknown patient"
                  ? "Your account was not found. Please log out and log in again."
                  : error}
              </Alert>
            </div>
          )}
        </section>

        {/* Conversation card */}
        <section className="flex min-h-[22rem] flex-col rounded-2xl border border-slate-200 bg-white shadow-sm md:min-h-[32rem]">
          <div className="border-b border-slate-100 px-5 py-3">
            <h2 className="text-sm font-semibold text-slate-900">Conversation</h2>
          </div>

          {!showCaptions ? (
            <div className="flex flex-1 items-center justify-center p-6 text-sm text-slate-500">
              Captions are off. The assistant is still speaking to you.
            </div>
          ) : visible.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
              <p className="text-sm text-slate-500">
                {status === "connected"
                  ? "Say hello to get started."
                  : "Press Start call and talk to the receptionist. You could say:"}
              </p>
              {status !== "connected" && (
                <ul className="space-y-1.5 text-sm text-slate-600">
                  {EXAMPLES.map((example) => (
                    <li key={example} className="rounded-full bg-sky-50 px-3 py-1">
                      “{example}”
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <div
              ref={logRef}
              role="log"
              aria-live="polite"
              className="flex flex-1 flex-col gap-2 overflow-y-auto p-4"
              style={{ maxHeight: "32rem" }}
            >
              {visible.map((line) => (
                <div
                  key={line.id}
                  className={`max-w-[85%] whitespace-pre-wrap break-words rounded-2xl px-3.5 py-2 text-sm ${BUBBLE[line.role]}`}
                >
                  {line.text}
                </div>
              ))}
            </div>
          )}
        </section>
      </main>

      {payment && <PaymentModal details={payment.details} onDone={finishPayment} />}
    </div>
  );
}