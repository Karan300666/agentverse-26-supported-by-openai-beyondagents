const API_URL = process.env.NEXT_PUBLIC_API_URL;

export type Patient = { id: string; name: string; age: number; phone: string };

export type VoiceSession = {
  session_id: string;
  client_secret: string;
  expires_in_seconds: number;
};

export type ToolCallResult = {
  ok: boolean;
  data: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// `phone` is sent as the X-Patient-Phone header. Login and register don't need it.
async function request<T>(path: string, phone: string | null, init: RequestInit = {}): Promise<T> {
  if (!API_URL) throw new Error("NEXT_PUBLIC_API_URL is not set");

  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(phone ? { "X-Patient-Phone": phone } : {}),
      ...(init.headers ?? {}),
    },
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `Request failed (${res.status})`;
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export function registerPatient(input: { name: string; age: number; phone: string }) {
  return request<Patient>("/auth/register", null, { method: "POST", body: JSON.stringify(input) });
}

export function loginPatient(phone: string) {
  return request<Patient>("/auth/login", null, { method: "POST", body: JSON.stringify({ phone }) });
}

export function createVoiceSession(phone: string) {
  return request<VoiceSession>("/voice/session", phone, { method: "POST" });
}

export function callTool(phone: string, sessionId: string, toolName: string, args: string) {
  return request<ToolCallResult>("/voice/tool-call", phone, {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, tool_name: toolName, arguments: args }),
  });
}

export function endVoiceSession(phone: string, sessionId: string, keepalive = false) {
  return request<void>(`/voice/session/${sessionId}`, phone, { method: "DELETE", keepalive });
}