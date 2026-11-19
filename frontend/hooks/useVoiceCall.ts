"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { callTool, createVoiceSession, endVoiceSession, type ToolCallResult } from "@/lib/api";
import { recordLatency } from "@/lib/latency";

const REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls";
const RECORD_LATENCY = process.env.NEXT_PUBLIC_SHOW_METRICS === "true";

export type CallStatus = "idle" | "connecting" | "connected" | "error";

/** What is happening in the conversation right now (while connected). */
export type Activity = "ready" | "listening" | "thinking" | "speaking";

export type TranscriptLine = {
  id: string;
  role: "patient" | "assistant" | "tool";
  text: string;
};

export type PaymentDetails = {
  amount: number;
  currency: string;
  doctor: string;
  specialty: string;
  date: string; // YYYY-MM-DD
  time: string; // HH:MM
};

/** A completed booking, cancellation or reschedule, as confirmed by the backend. */
export type Confirmation = {
  kind: "booked" | "cancelled" | "rescheduled";
  doctor: string;
  specialty: string;
  date: string; // YYYY-MM-DD
  time: string; // HH:MM
  feeAmount: number | null;
  currency: string;
};

type Options = {
  /** Resolves true if the (simulated) payment was completed, false if the patient cancelled. */
  requestPayment: (details: PaymentDetails) => Promise<boolean>;
};

type FunctionCallItem = {
  type: string;
  name?: string;
  call_id?: string;
  arguments?: string;
};

const CONFIRMED_STATUSES = new Set(["booked", "cancelled", "rescheduled"]);

function confirmationCodeOf(args: string): string | undefined {
  try {
    const parsed = JSON.parse(args) as { confirmation_code?: unknown };
    return typeof parsed.confirmation_code === "string" ? parsed.confirmation_code : undefined;
  } catch {
    return undefined;
  }
}

function toPaymentDetails(data: Record<string, unknown> | null): PaymentDetails | null {
  const summary = data?.summary as Record<string, unknown> | undefined;
  if (!summary) return null;
  const amount = Number(summary.fee_amount);
  if (!Number.isFinite(amount)) return null;
  return {
    amount,
    currency: String(summary.currency ?? "INR"),
    doctor: String(summary.doctor ?? ""),
    specialty: String(summary.specialty ?? ""),
    date: String(summary.date ?? ""),
    time: String(summary.time ?? ""),
  };
}

function toConfirmation(data: Record<string, unknown> | null): Confirmation | null {
  const status = data?.status;
  const appointment = data?.appointment as Record<string, unknown> | undefined;
  if (typeof status !== "string" || !CONFIRMED_STATUSES.has(status) || !appointment) return null;
  const fee = Number(appointment.fee_amount);
  return {
    kind: status as Confirmation["kind"],
    doctor: String(appointment.doctor ?? ""),
    specialty: String(appointment.specialty ?? ""),
    date: String(appointment.date ?? ""),
    time: String(appointment.time ?? ""),
    feeAmount: Number.isFinite(fee) ? fee : null,
    currency: String(appointment.currency ?? "INR"),
  };
}

export function useVoiceCall({ requestPayment }: Options) {
  const [status, setStatus] = useState<CallStatus>("idle");
  const [activity, setActivity] = useState<Activity>("ready");
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [muted, setMuted] = useState(false);
  const [connectedAt, setConnectedAt] = useState<number | null>(null);
  const [pendingTools, setPendingTools] = useState(0);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionRef = useRef<{ id: string; phone: string } | null>(null);
  const handledCalls = useRef<Set<string>>(new Set());
  const speechStoppedAt = useRef<number | null>(null);
  const toolsThisTurn = useRef(0);
  const pendingSample = useRef<number | null>(null);

  /** Save the previous turn's time once we know whether it used tools. */
  const flushSample = useCallback(() => {
    if (pendingSample.current !== null && RECORD_LATENCY) {
      recordLatency(pendingSample.current, toolsThisTurn.current > 0);
    }
    pendingSample.current = null;
  }, []);
  const proposals = useRef<Map<string, PaymentDetails>>(new Map());
  const mutedRef = useRef(false);
  const requestPaymentRef = useRef(requestPayment);

  useEffect(() => {
    requestPaymentRef.current = requestPayment;
  }, [requestPayment]);

  const addLine = useCallback((line: TranscriptLine) => {
    setTranscript((prev) => (prev.some((l) => l.id === line.id) ? prev : [...prev, line]));
  }, []);

  const sendEvent = useCallback((event: unknown) => {
    const dc = dcRef.current;
    if (dc && dc.readyState === "open") dc.send(JSON.stringify(event));
  }, []);

  /** Runs one tool call on the backend. A confirmed booking waits for the simulated payment first. */
  const runToolCall = useCallback(async (name: string, args: string): Promise<ToolCallResult> => {
    const session = sessionRef.current;
    if (!session) throw new Error("No active session");

    if (name === "book_appointment") {
      const code = confirmationCodeOf(args);
      const details = code ? proposals.current.get(code) : undefined;
      if (code && details && details.amount > 0) {
        const paid = await requestPaymentRef.current(details);
        proposals.current.delete(code);
        if (!paid) {
          return {
            ok: false,
            data: null,
            error: {
              code: "payment_cancelled",
              message: "The patient did not complete the payment, so nothing was booked.",
            },
          };
        }
      }
    }

    const result = await callTool(session.phone, session.id, name, args);

    if (name === "book_appointment" && result.ok && result.data?.status === "confirmation_required") {
      const code = result.data.confirmation_code;
      const details = toPaymentDetails(result.data);
      if (typeof code === "string" && details) proposals.current.set(code, details);
    }

    if (result.ok) {
      const done = toConfirmation(result.data);
      if (done) setConfirmation(done);
    }
    return result;
  }, []);

  const handleToolCalls = useCallback(
    async (calls: FunctionCallItem[]) => {
      const fresh = calls.filter((c) => c.call_id && !handledCalls.current.has(c.call_id));
      if (fresh.length === 0) return;
      fresh.forEach((c) => handledCalls.current.add(c.call_id as string));
      toolsThisTurn.current += fresh.length;

      setPendingTools((n) => n + fresh.length);
      await Promise.all(
        fresh.map(async (call) => {
          const callId = call.call_id as string;
          const name = call.name ?? "";
          const args = call.arguments ?? "{}";

          let result: ToolCallResult;
          try {
            result = await runToolCall(name, args);
          } catch {
            result = {
              ok: false,
              data: null,
              error: { code: "internal_error", message: "Something went wrong. Please try again." },
            };
          }

          addLine({
            id: `tool-${callId}`,
            role: "tool",
            text: `${name}(${args}) -> ${result.ok ? "ok" : result.error?.code}\n${JSON.stringify(
              result.ok ? result.data : result.error,
            )}`,
          });
          sendEvent({
            type: "conversation.item.create",
            item: { type: "function_call_output", call_id: callId, output: JSON.stringify(result) },
          });
          setPendingTools((n) => Math.max(0, n - 1));
        }),
      );

      // One response after all tool results are in.
      sendEvent({ type: "response.create" });
    },
    [addLine, runToolCall, sendEvent],
  );

  const handleMessage = useCallback(
    (message: MessageEvent) => {
      let event: Record<string, unknown>;
      try {
        event = JSON.parse(message.data as string);
      } catch {
        return;
      }

      switch (event.type) {
        case "input_audio_buffer.speech_started":
          setActivity("listening");
          break;
        case "input_audio_buffer.speech_stopped":
          flushSample(); // the previous turn is over: save it with its tool count
          speechStoppedAt.current = performance.now();
          toolsThisTurn.current = 0;
          setActivity("thinking");
          break;
        case "output_audio_buffer.started":
          if (speechStoppedAt.current !== null) {
            pendingSample.current = Math.round(performance.now() - speechStoppedAt.current);
          }
          speechStoppedAt.current = null;
          setActivity("speaking");
          break;
          speechStoppedAt.current = null;
          setActivity("speaking");
          break;
        case "output_audio_buffer.stopped":
        case "output_audio_buffer.cleared":
          // Don't overwrite "listening" when the patient interrupted the assistant.
          setActivity((prev) => (prev === "speaking" ? "ready" : prev));
          break;
        case "conversation.item.input_audio_transcription.completed":
          addLine({
            id: `patient-${event.item_id}`,
            role: "patient",
            text: String(event.transcript ?? ""),
          });
          break;
        // The event name differs between API versions, so both are handled.
        case "response.output_audio_transcript.done":
        case "response.audio_transcript.done":
          addLine({
            id: `assistant-${event.item_id}`,
            role: "assistant",
            text: String(event.transcript ?? ""),
          });
          break;
        case "response.done": {
          const response = event.response as { output?: FunctionCallItem[] } | undefined;
          const calls = (response?.output ?? []).filter(
            (item) => item.type === "function_call" && item.call_id && item.name,
          );
          if (calls.length > 0) void handleToolCalls(calls);
          break;
        }
      }
    },
    [addLine, flushSample, handleToolCalls],
  );

  const cleanup = useCallback(() => {
     flushSample();
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    dcRef.current?.close();
    pcRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    if (audioRef.current) audioRef.current.srcObject = null;
    dcRef.current = null;
    pcRef.current = null;
    streamRef.current = null;
    handledCalls.current.clear();
    proposals.current.clear();
    speechStoppedAt.current = null;
    mutedRef.current = false;
    setMuted(false);
    setConnectedAt(null);
    setPendingTools(0);
    setActivity("ready");
  }, [flushSample]);

  const disconnect = useCallback(async () => {
    const session = sessionRef.current;
    cleanup();
    sessionRef.current = null;
    setStatus("idle");
    if (session) {
      try {
        await endVoiceSession(session.phone, session.id);
      } catch {
        /* best effort */
      }
    }
  }, [cleanup]);

  const toggleMute = useCallback(() => {
    const stream = streamRef.current;
    if (!stream) return;
    const next = !mutedRef.current;
    mutedRef.current = next;
    stream.getAudioTracks().forEach((track) => {
      track.enabled = !next;
    });
    setMuted(next);
  }, []);

  const dismissConfirmation = useCallback(() => setConfirmation(null), []);

  const connect = useCallback(
    async (phone: string) => {
      setStatus("connecting");
      setError(null);
      setTranscript([]);
      setConfirmation(null);
      try {
        const session = await createVoiceSession(phone);
        sessionRef.current = { id: session.session_id, phone };

        // Hang up automatically when the session's maximum length is reached.
        timerRef.current = setTimeout(() => {
          setError("The call reached its maximum length.");
          void disconnect();
        }, session.expires_in_seconds * 1000);

        const pc = new RTCPeerConnection();
        pcRef.current = pc;

        const audio = new Audio();
        audio.autoplay = true;
        audioRef.current = audio;
        pc.ontrack = (e) => {
          audio.srcObject = e.streams[0];
        };

        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streamRef.current = stream;
        stream.getTracks().forEach((track) => pc.addTrack(track, stream));

        const dc = pc.createDataChannel("oai-events");
        dcRef.current = dc;
        dc.onmessage = handleMessage;
        dc.onopen = () => {
          setStatus("connected");
          setActivity("ready");
          setConnectedAt(Date.now());
        };

        const offer = await pc.createOffer();
        await pc.setLocalDescription(offer);

        const sdpResponse = await fetch(REALTIME_CALLS_URL, {
          method: "POST",
          body: offer.sdp,
          headers: {
            Authorization: `Bearer ${session.client_secret}`,
            "Content-Type": "application/sdp",
          },
        });
        if (!sdpResponse.ok) {
          throw new Error(`Could not connect to the voice service (${sdpResponse.status})`);
        }
        await pc.setRemoteDescription({ type: "answer", sdp: await sdpResponse.text() });
      } catch (err) {
        const session = sessionRef.current;
        cleanup();
        sessionRef.current = null;

        let message = "Could not start the call.";
        if (err instanceof DOMException && err.name === "NotAllowedError") {
          message = "Microphone access was blocked. Allow the microphone in your browser settings and try again.";
        } else if (err instanceof DOMException && err.name === "NotFoundError") {
          message = "No microphone was found on this device.";
        } else if (err instanceof Error) {
          message = err.message;
        }
        setError(message);
        setStatus("error");

        if (session) {
          // Free the patient's single call slot if the connection failed after the session started.
          void endVoiceSession(session.phone, session.id).catch(() => { });
        }
      }
    },
    [cleanup, disconnect, handleMessage],
  );

  // Best effort: end the session if the tab is closed during a call.
  useEffect(() => {
    const onPageHide = () => {
      const session = sessionRef.current;
      if (session) void endVoiceSession(session.phone, session.id, true).catch(() => { });
    };
    window.addEventListener("pagehide", onPageHide);
    return () => window.removeEventListener("pagehide", onPageHide);
  }, []);

  return {
    status,
    activity,
    error,
    transcript,
    muted,
    connectedAt,
    pendingTools,
    confirmation,
    connect,
    disconnect,
    toggleMute,
    dismissConfirmation,
  };
}