import { api, fmtDate, toast } from "../api";
import { usePoll } from "../hooks";
import JobProgress, { StatusChip } from "../components/JobProgress";
import type { Job } from "../types";

export default function JobsPage() {
  const { data, refresh } = usePoll<Job[]>(() => api.get("/api/jobs"), 2000);
  const jobs = data || [];
  const active = jobs.some((j) => j.status === "queued" || j.status === "running");

  const cancel = async (j: Job) => {
    try {
      await api.post(`/api/jobs/${j.id}/cancel`);
      toast(`Job ${j.id} canceled`);
      refresh();
    } catch (e) { toast(e instanceof Error ? e.message : "failed", "err"); }
  };

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Job queue</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Model analysis and V-Ray render jobs{active ? " — polling live…" : "."}
          </p>
        </div>
        <span className={`rounded-full border px-3 py-1 text-xs ${active ? "border-amber-500/40 bg-amber-500/10 text-amber-300" : "border-zinc-700 text-zinc-500"}`}>
          {active ? `${jobs.filter((j) => j.status === "queued" || j.status === "running").length} active` : "idle"}
        </span>
      </header>

      <div className="space-y-3">
        {jobs.map((j) => (
          <div key={j.id} className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="mb-3 flex items-center gap-3">
              <span className="rounded bg-zinc-800 px-2 py-0.5 text-[11px] uppercase tracking-wide text-zinc-400">#{j.id} {j.kind}</span>
              <span className="truncate text-sm text-zinc-200">{j.model_name}</span>
              <span className="ml-auto text-[11px] text-zinc-600">{fmtDate(j.created_at)}</span>
              <StatusChip status={j.status} />
              {(j.status === "queued" || j.status === "running") && (
                <button onClick={() => cancel(j)} className="rounded-lg border border-zinc-700 px-2.5 py-1 text-[11px] text-zinc-400 hover:border-red-900 hover:text-red-400">
                  Cancel
                </button>
              )}
            </div>
            <JobProgress job={j} />
          </div>
        ))}
        {jobs.length === 0 && <p className="py-20 text-center text-sm text-zinc-500">No jobs yet.</p>}
      </div>
    </div>
  );
}
