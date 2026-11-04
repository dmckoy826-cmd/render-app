import { useEffect, useState } from "react";
import Modal from "./Modal";
import JobProgress from "./JobProgress";
import { api, toast } from "../api";
import type { Job } from "../types";

const RESOLUTIONS = [
  { label: "HD 1280×720", w: 1280, h: 720 },
  { label: "FHD 1920×1080", w: 1920, h: 1080 },
  { label: "QHD 2560×1440", w: 2560, h: 1440 },
  { label: "Square 1600×1600", w: 1600, h: 1600 },
];

export default function RenderDialog({ open, onClose, modelId, onDone }: {
  open: boolean; onClose: () => void; modelId: number; onDone: () => void;
}) {
  const [w, setW] = useState(1920);
  const [h, setH] = useState(1080);
  const [quality, setQuality] = useState<"draft" | "standard" | "high">("standard");
  const [camera, setCamera] = useState<"iso" | "front" | "top">("iso");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);

  const active = job && !["done", "failed", "canceled"].includes(job.status);

  useEffect(() => {
    if (!open) { setJob(null); setBusy(false); }
  }, [open]);

  useEffect(() => {
    if (!job || !active) return;
    const t = setInterval(async () => {
      try {
        const j = await api.get(`/api/jobs/${job.id}`);
        setJob(j);
        if (j.status === "done") { toast("Render finished — see Renders tab"); onDone(); }
        if (j.status === "failed") toast(`Render failed: ${j.error}`, "err");
      } catch { /* ignore */ }
    }, 1200);
    return () => clearInterval(t);
  }, [job?.id, active]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = async () => {
    setBusy(true);
    try {
      const j = await api.post("/api/jobs/render", { model_id: modelId, settings: { width: w, height: h, quality, camera } });
      setJob(j);
    } catch (e) {
      toast(e instanceof Error ? e.message : "failed", "err");
    }
    setBusy(false);
  };

  return (
    <Modal open={open} onClose={onClose} title="Render with V-Ray">
      {job && active ? (
        <JobProgress job={job} />
      ) : (
        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">Resolution</label>
            <div className="flex flex-wrap gap-2">
              {RESOLUTIONS.map((r) => (
                <button key={r.label} onClick={() => { setW(r.w); setH(r.h); }}
                  className={`rounded-lg border px-3 py-1.5 text-xs ${w === r.w && h === r.h ? "border-amber-500/60 bg-amber-500/10 text-amber-300" : "border-zinc-700 text-zinc-400 hover:border-zinc-500"}`}>
                  {r.label}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">Quality</label>
              <select value={quality} onChange={(e) => setQuality(e.target.value as any)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60">
                <option value="draft">Draft (fast)</option>
                <option value="standard">Standard</option>
                <option value="high">High (slow)</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">Camera</label>
              <select value={camera} onChange={(e) => setCamera(e.target.value as any)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60">
                <option value="iso">Isometric</option>
                <option value="front">Front elevation</option>
                <option value="top">Top / plan</option>
              </select>
            </div>
          </div>
          <p className="rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-500">
            Finishes are applied at their real-world swatch scale. Parts inside block definitions are
            updated through BlockEdit on the Rhino worker.
          </p>
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
            <button onClick={submit} disabled={busy}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:opacity-50">
              {busy ? "Queueing…" : "Queue render"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
