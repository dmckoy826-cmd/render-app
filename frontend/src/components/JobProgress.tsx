import type { Job } from "../types";

export type ChipStatus = Job["status"] | "uploaded" | "analyzing" | "ready";

export function StatusChip({ status }: { status: ChipStatus }) {
  const map: Record<ChipStatus, string> = {
    queued: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
    running: "bg-amber-500/15 text-amber-300 border-amber-500/30 animate-pulse",
    analyzing: "bg-amber-500/15 text-amber-300 border-amber-500/30 animate-pulse",
    done: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    ready: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    uploaded: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
    failed: "bg-red-500/15 text-red-300 border-red-500/30",
    canceled: "bg-zinc-500/15 text-zinc-400 border-zinc-600/30",
  };
  return <span className={`rounded border px-2 py-0.5 text-[11px] capitalize ${map[status]}`}>{status}</span>;
}

export default function JobProgress({ job }: { job: Job }) {
  const bar = job.status === "failed" ? "bg-red-500" : job.status === "canceled" ? "bg-zinc-500"
    : job.status === "done" ? "bg-emerald-500" : "bg-amber-500";
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="mb-2 flex items-center justify-between gap-3 text-xs">
        <span className="truncate text-zinc-300">
          <span className="mr-2 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">{job.kind}</span>
          {job.stage || "…"}
        </span>
        <StatusChip status={job.status} />
      </div>
      <div className="h-2 overflow-hidden rounded bg-zinc-800">
        <div className={`h-full transition-all duration-500 ${bar}`} style={{ width: `${job.progress}%` }} />
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-zinc-500">
        <span>{job.runner === "mock" ? "simulated engine" : "rhino agent"}</span>
        <span>{job.progress}%</span>
      </div>
      {job.error && <p className="mt-2 text-xs text-red-400">{job.error}</p>}
    </div>
  );
}
