const KEY = "hospital-voice-latency";

export type LatencySample = { ms: number; tools: boolean; at: string };

export function loadLatencies(): LatencySample[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as LatencySample[]) : [];
  } catch {
    return [];
  }
}

export function recordLatency(ms: number, tools: boolean): void {
  try {
    const all = loadLatencies();
    all.push({ ms, tools, at: new Date().toISOString() });
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    /* storage unavailable: skip */
  }
}

export function clearLatencies(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

/** Nearest-rank percentile: p=50 is the median, p=95 is the slow tail. */
export function percentile(values: number[], p: number): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[index];
}

export function toCsv(samples: LatencySample[]): string {
  return ["ms,tools,at", ...samples.map((s) => `${s.ms},${s.tools},${s.at}`)].join("\n");
}