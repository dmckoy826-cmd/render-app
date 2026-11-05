import { useEffect, useState } from "react";
import Modal from "./Modal";
import JobProgress from "./JobProgress";
import { api, toast } from "../api";
import type { CameraPose, Job, SavedCameraView, SystemInfo } from "../types";
import { usePoll } from "../hooks";

const RESOLUTIONS = [
  { label: "HD 1280×720", w: 1280, h: 720 },
  { label: "FHD 1920×1080", w: 1920, h: 1080 },
  { label: "QHD 2560×1440", w: 2560, h: 1440 },
  { label: "Square 1600×1600", w: 1600, h: 1600 },
];

export default function RenderDialog({
  open, onClose, modelId, onDone, currentCameraPose, savedViews = [], namedViews = [],
}: {
  open: boolean;
  onClose: () => void;
  modelId: number;
  onDone: () => void;
  currentCameraPose?: CameraPose | null;
  savedViews?: SavedCameraView[];
  namedViews?: string[];
}) {
  const [w, setW] = useState(1920);
  const [h, setH] = useState(1080);
  const [quality, setQuality] = useState<"draft" | "standard" | "high">("standard");
  const [cameraChoice, setCameraChoice] = useState<string>("viewer");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: system } = usePoll<SystemInfo>(() => api.get("/api/system/info"), 5000, open);
  const realWorker = system?.runner === "agent";

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
      let camera: "iso" | "front" | "top" = "iso";
      let camera_pose: CameraPose | undefined;
      let named_view: string | undefined;

      if (cameraChoice === "viewer" && currentCameraPose) {
        camera = "iso";
        camera_pose = currentCameraPose;
      } else if (cameraChoice.startsWith("saved:")) {
        const name = cameraChoice.slice("saved:".length);
        const found = savedViews.find((v) => v.name === name);
        camera = "iso";
        if (found) camera_pose = found.pose;
      } else if (cameraChoice.startsWith("rhino:")) {
        camera = "iso";
        named_view = cameraChoice.slice("rhino:".length);
      } else if (cameraChoice === "front" || cameraChoice === "top" || cameraChoice === "iso") {
        camera = cameraChoice;
      }

      const j = await api.post("/api/jobs/render", {
        model_id: modelId,
        settings: {
          width: w,
          height: h,
          quality: realWorker ? "current" : quality,
          camera,
          ...(camera_pose ? { camera_pose } : {}),
          ...(named_view ? { named_view } : {}),
        },
      });
      setJob(j);
    } catch (e) {
      toast(e instanceof Error ? e.message : "failed", "err");
    }
    setBusy(false);
  };

  return (
    <Modal open={open} onClose={onClose} title={realWorker ? "Render via worker" : "Simulated render"}>
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
              {realWorker ? <div className="rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-300">Current V-Ray settings</div>
                : <select value={quality} onChange={(e) => setQuality(e.target.value as any)}
                  className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60">
                  <option value="draft">Draft (simulated)</option><option value="standard">Standard (simulated)</option>
                  <option value="high">High (simulated)</option>
                </select>}
            </div>
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">Camera View</label>
              <select value={cameraChoice} onChange={(e) => setCameraChoice(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60">
                {currentCameraPose && (
                  <option value="viewer">Current 3D viewer angle</option>
                )}
                {savedViews.length > 0 && (
                  <optgroup label="Saved UI views">
                    {savedViews.map((sv) => (
                      <option key={`saved:${sv.name}`} value={`saved:${sv.name}`}>{sv.name}</option>
                    ))}
                  </optgroup>
                )}
                {namedViews.length > 0 && (
                  <optgroup label="Rhino Named Views (from file)">
                    {namedViews.map((nv) => (
                      <option key={`rhino:${nv}`} value={`rhino:${nv}`}>{nv}</option>
                    ))}
                  </optgroup>
                )}
                <optgroup label="Standard projections (auto-fit)">
                  <option value="iso">Perspective (auto-fit)</option>
                  <option value="front">Front elevation</option>
                  <option value="top">Top / plan</option>
                </optgroup>
              </select>
            </div>
          </div>
          {cameraChoice === "viewer" && currentCameraPose && (
            <div className="rounded-lg border border-emerald-800/50 bg-emerald-950/20 px-3 py-2 text-[11px] text-emerald-200">
              Using your exact 3D viewer angle — eye ({currentCameraPose.eye.map((n) => Math.round(n * 10) / 10).join(", ")}) in → target ({currentCameraPose.target.map((n) => Math.round(n * 10) / 10).join(", ")}) in.
            </div>
          )}
          <p className="rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-500">
            {realWorker
              ? "The worker attempts V-Ray rendering, real-world mapping and safe BlockEdit; shared or unsupported targets fail rather than silently changing other parts. V-Ray uses its current quality settings."
              : "This job uses the simulated engine, not V-Ray. Connect the Rhino worker for local rendering."}
          </p>
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
            <button onClick={submit} disabled={busy || !system}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:opacity-50">
              {busy ? "Queueing…" : "Queue render"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
