"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { clearLatencies, loadLatencies, percentile, toCsv, type LatencySample } from "@/lib/latency";

function Row({ label, samples }: { label: string; samples: LatencySample[] }) {
  const ms = samples.map((s) => s.ms);
  const fmt = (v: number | null) => (v === null ? "–" : `${(v / 1000).toFixed(2)} s`);
  return (
    <div className="flex justify-between gap-3">
      <span className="text-slate-500">
        {label} ({samples.length})
      </span>
      <span className="font-mono">
        p50 {fmt(percentile(ms, 50))} · p95 {fmt(percentile(ms, 95))}
      </span>
    </div>
  );
}

export default function LatencyStats() {
  const [samples, setSamples] = useState<LatencySample[]>([]);

  useEffect(() => {
    setSamples(loadLatencies());
    const id = setInterval(() => setSamples(loadLatencies()), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="w-full space-y-1.5 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs">
      <p className="font-semibold text-slate-700">Response time (stop speaking → reply starts)</p>
      <Row label="All turns" samples={samples} />
      <Row label="With tools" samples={samples.filter((s) => s.tools)} />
      <Row label="Without tools" samples={samples.filter((s) => !s.tools)} />
      <div className="flex gap-2 pt-1">
        <Button variant="secondary" className="!py-1 text-xs" onClick={() => void navigator.clipboard.writeText(toCsv(samples))}>
          Copy CSV
        </Button>
        <Button
          variant="secondary"
          className="!py-1 text-xs"
          onClick={() => {
            if (confirm("Delete all recorded response times?")) {
              clearLatencies();
              setSamples([]);
            }
          }}
        >
          Reset
        </Button>
      </div>
    </div>
  );
}