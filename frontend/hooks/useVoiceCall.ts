"use client";

import { useCallback, useRef, useState } from "react";
import { callTool, createVoiceSession, endVoiceSession, type ToolCallResult } from "@/lib/api";

const REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls";

export type CallStatus = "idle" | "connecting" | "connected" | "error";
export type TranscriptLine = {
  id: string;
  role: "patient" | "assistant" | "tool";
  text: string;
};

type FunctionCallItem = {
  type: string;
  name?: string;
  call_id?: string;
  arguments?: string;
};

export function useVoiceCall() {
  const [status, setStatus] = useState<CallStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const sessionRef = useRef<{ id: string; phone: string } | null>(null);
  const handledCalls = useRef<Set<string>>(new Set());

  const addLine = useCallback((line: TranscriptLine) => {
    setTranscript((prev) => (prev.some((l) => l.id === line.id) ? prev : [...prev, line]));
  }, []);

  const sendEvent = useCallback((event: unknown) => {
    const dc = dcRef.current;
    if (dc && dc.readyState === "open") dc.send(JSON.stringify(event));
  }, []);

  const handleToolCalls = useCallback(
    async (calls: FunctionCallItem[]) => {
      const fresh = calls.filter((c) => c.call_id && !handledCalls.current.has(c.call_id));
      if (fresh.length === 0) return;
      fresh.forEach((c) => handledCalls.current.add(c.call_id as string));

      await Promise.all(
        fresh.map(async (call) => {
          const callId = call.call_id as string;
          const name = call.name ?? "";
          const args = call.arguments ?? "{}";

          let result: ToolCallResult;
          try {
            const session = sessionRef.current;
            if (!session) throw new Error("No active session");
            result = await callTool(session.phone, session.id, name, args);
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
        }),
      );

      // One response after all tool results are in.
      sendEvent({ type: "response.create" });
    },
    [addLine, sendEvent],
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
    [addLine, handleToolCalls],
  );

  const cleanup = useCallback(() => {
    dcRef.current?.close();
    pcRef.current?.close();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    if (audioRef.current) audioRef.current.srcObject = null;
    dcRef.current = null;
    pcRef.current = null;
    streamRef.current = null;
    handledCalls.current.clear();
  }, []);

  const connect = useCallback(
    async (phone: string) => {
      setStatus("connecting");
      setError(null);
      setTranscript([]);
      try {
        const session = await createVoiceSession(phone);
        sessionRef.current = { id: session.session_id, phone };

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
        dc.onopen = () => setStatus("connected");

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
        cleanup();
        setError(err instanceof Error ? err.message : "Could not start the call");
        setStatus("error");
      }
    },
    [cleanup, handleMessage],
  );

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

  return { status, error, transcript, connect, disconnect };
}