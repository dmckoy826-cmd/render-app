import { useEffect, useMemo, useState } from "react";
import Modal from "./Modal";
import JobProgress from "./JobProgress";
import { api, toast } from "../api";
import { CATEGORY_LABEL, type Assignment, type CameraPose, type Category, type Finish, type Job, type LayerInfo, type SavedCameraView, type SkuLayerInfo, type SystemInfo } from "../types";
import { usePoll } from "../hooks";

const RESOLUTIONS = [
  { label: "HD 1280×720", w: 1280, h: 720 },
  { label: "FHD 1920×1080", w: 1920, h: 1080 },
  { label: "QHD 2560×1440", w: 2560, h: 1440 },
  { label: "Square 1600×1600", w: 1600, h: 1600 },
];

const OUT_DIR_STORAGE_KEY = "ff_batch_output_dir_v1";

interface QueuedFinishItem {
  finish_id: number;
  scale_multiplier: number;
  extra_layer?: string;
  extra_finish_id?: number | null;
  extra_scale?: number;
}

export default function RenderDialog({
  open, onClose, modelId, onDone, initialMode = "single",
  currentCameraPose, savedViews = [], namedViews = [],
  skuLayers = [], partLayers = [], assignments = [],
}: {
  open: boolean;
  onClose: () => void;
  modelId: number;
  onDone: () => void;
  initialMode?: "single" | "batch";
  currentCameraPose?: CameraPose | null;
  savedViews?: SavedCameraView[];
  namedViews?: string[];
  skuLayers?: SkuLayerInfo[];
  partLayers?: LayerInfo[];
  assignments?: Assignment[];
}) {
  const [mode, setMode] = useState<"single" | "batch">(initialMode);
  const [w, setW] = useState(1920);
  const [h, setH] = useState(1080);
  const [useFileVray, setUseFileVray] = useState(false);
  const [quality, setQuality] = useState<"draft" | "standard" | "high">("standard");
  const [cameraChoice, setCameraChoice] = useState<string>("viewer");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);

  // Batch state
  const [outputDir, setOutputDir] = useState<string>(() => {
    try { return localStorage.getItem(OUT_DIR_STORAGE_KEY) || ""; } catch { return ""; }
  });
  const [selectedSkus, setSelectedSkus] = useState<Set<string>>(new Set());
  const [varyingLayer, setVaryingLayer] = useState<string>("");
  const [secondVaryingLayer, setSecondVaryingLayer] = useState<string>("");
  const [queuedFinishes, setQueuedFinishes] = useState<QueuedFinishItem[]>([]);
  const [finishFilterCat, setFinishFilterCat] = useState<"all" | Category>("all");
  const [finishSearch, setFinishSearch] = useState("");

  const { data: system } = usePoll<SystemInfo>(() => api.get("/api/system/info"), 5000, open);
  const { data: allFinishes } = usePoll<Finish[]>(() => api.get("/api/finishes"), 30000, open);
  const realWorker = system?.runner === "agent";

  // Candidate SKU layers: use structure.sku_layers if present, otherwise fallback to partLayers
  const availableSkus = useMemo(() => {
    if (skuLayers.length > 0) return skuLayers.map((s) => s.name);
    return partLayers.map((l) => l.name);
  }, [skuLayers, partLayers]);

  useEffect(() => {
    if (open) {
      setMode(initialMode);
      setJob(null);
      setBusy(false);
      setSelectedSkus(new Set(availableSkus));
      if (!varyingLayer && partLayers.length > 0) {
        setVaryingLayer(partLayers[0].name);
      }
      if (initialMode === "batch") {
        setUseFileVray(true);
        if (namedViews.length > 0) setCameraChoice(`rhino:${namedViews[0]}`);
        else setCameraChoice("file_active");
      }
    }
  }, [open, initialMode, availableSkus, partLayers, namedViews]); // eslint-disable-line react-hooks/exhaustive-deps

  const active = job && !["done", "failed", "canceled"].includes(job.status);

  useEffect(() => {
    if (!job || !active) return;
    const t = setInterval(async () => {
      try {
        const j = await api.get(`/api/jobs/${job.id}`);
        setJob(j);
        if (j.status === "done") {
          const count = j.settings?.saved_files?.length;
          toast(count ? `Batch finished — saved ${count} PNGs to ${j.settings?.output_dir}` : "Render finished — see Renders tab");
          onDone();
        }
        if (j.status === "failed") toast(`Render failed: ${j.error}`, "err");
      } catch { /* ignore */ }
    }, 1200);
    return () => clearInterval(t);
  }, [job?.id, active]); // eslint-disable-line react-hooks/exhaustive-deps

  const browseFolder = async () => {
    try {
      const res = await api.get("/api/system/pick-folder");
      if (res?.path) {
        setOutputDir(res.path);
        try { localStorage.setItem(OUT_DIR_STORAGE_KEY, res.path); } catch { /* ignore */ }
      }
    } catch {
      toast("Could not open folder picker — paste folder path directly", "err");
    }
  };

  const toggleQueuedFinish = (f: Finish) => {
    setQueuedFinishes((prev) => {
      const exists = prev.find((x) => x.finish_id === f.id);
      if (exists) return prev.filter((x) => x.finish_id !== f.id);
      // Default scale: if this layer already has this finish assigned, use its scale, else 1
      const existingAssign = assignments.find((a) => a.target_kind === "layer" && a.target_name === varyingLayer);
      const defaultScale = existingAssign?.scale_multiplier || 1;
      return [...prev, { finish_id: f.id, scale_multiplier: defaultScale }];
    });
  };

  const updateQueuedScale = (finishId: number, scale: number) => {
    if (!Number.isFinite(scale) || scale <= 0) return;
    setQueuedFinishes((prev) => prev.map((x) => (x.finish_id === finishId ? { ...x, scale_multiplier: scale } : x)));
  };

  const filteredFinishes = useMemo(() => {
    return (allFinishes || []).filter((f) =>
      (finishFilterCat === "all" || f.category === finishFilterCat) &&
      (!finishSearch || `${f.name} ${f.tags}`.toLowerCase().includes(finishSearch.toLowerCase())),
    );
  }, [allFinishes, finishFilterCat, finishSearch]);

  const finishById = useMemo(() => new Map((allFinishes || []).map((f) => [f.id, f])), [allFinishes]);

  const submit = async () => {
    setBusy(true);
    try {
      let camera: "iso" | "front" | "top" = "iso";
      let camera_pose: CameraPose | undefined;
      let named_view: string | undefined;
      let keep_file_view = false;

      if (cameraChoice === "file_active") {
        camera = "iso";
        keep_file_view = true;
      } else if (cameraChoice === "viewer" && currentCameraPose) {
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

      let batchPayload: Record<string, any> | undefined;
      if (mode === "batch") {
        if (!outputDir.trim()) {
          toast("Select or enter an output folder path first", "err");
          setBusy(false);
          return;
        }
        const skuList = availableSkus.filter((s) => selectedSkus.has(s));
        if (!skuList.length) {
          toast("Select at least one SKU layer to render", "err");
          setBusy(false);
          return;
        }
        if (!varyingLayer) {
          toast("Select the part layer whose finish changes between renders", "err");
          setBusy(false);
          return;
        }
        if (!queuedFinishes.length) {
          toast("Queue at least one finish variation to render", "err");
          setBusy(false);
          return;
        }
        try { localStorage.setItem(OUT_DIR_STORAGE_KEY, outputDir.trim()); } catch { /* ignore */ }

        const base_assignments = assignments
          .filter((a) => a.target_kind === "layer" && a.target_name !== varyingLayer && a.target_name !== secondVaryingLayer && a.finish_id)
          .map((a) => ({
            target_kind: "layer",
            target_name: a.target_name,
            finish_id: a.finish_id,
            scale_multiplier: a.scale_multiplier || 1,
          }));

        const variations = queuedFinishes.map((qf) => {
          const fin = finishById.get(qf.finish_id);
          const extraFin = secondVaryingLayer && qf.extra_finish_id ? finishById.get(qf.extra_finish_id) : undefined;
          const labelParts = [fin?.name || `Finish_${qf.finish_id}`];
          const overrides = [
            {
              target_kind: "layer",
              target_name: varyingLayer,
              finish_id: qf.finish_id,
              scale_multiplier: qf.scale_multiplier || 1,
            },
          ];
          if (secondVaryingLayer && extraFin) {
            labelParts.push(extraFin.name);
            overrides.push({
              target_kind: "layer",
              target_name: secondVaryingLayer,
              finish_id: extraFin.id,
              scale_multiplier: qf.extra_scale || 1,
            });
          }
          return {
            label: labelParts.join(" - "),
            overrides,
          };
        });

        batchPayload = {
          output_dir: outputDir.trim(),
          sku_layers: skuList,
          base_assignments,
          variations,
        };
      }

      const j = await api.post("/api/jobs/render", {
        model_id: modelId,
        settings: {
          width: w,
          height: h,
          quality: realWorker ? "current" : quality,
          camera,
          keep_file_view,
          use_file_vray_settings: useFileVray,
          ...(camera_pose ? { camera_pose } : {}),
          ...(named_view ? { named_view } : {}),
          ...(batchPayload ? { batch: batchPayload } : {}),
        },
      });
      setJob(j);
    } catch (e) {
      toast(e instanceof Error ? e.message : "failed", "err");
    }
    setBusy(false);
  };

  return (
    <Modal open={open} onClose={onClose} title={mode === "batch" ? "Batch SKU × Finish Queue Render" : (realWorker ? "Render via worker" : "Simulated render")} wide={mode === "batch"}>
      {job && active ? (
        <JobProgress job={job} />
      ) : (
        <div className="space-y-4">
          {/* Mode selector */}
          <div className="flex rounded-lg border border-zinc-800 bg-zinc-950 p-1">
            <button
              type="button"
              onClick={() => setMode("single")}
              className={`flex-1 rounded-md py-1.5 text-xs font-medium ${mode === "single" ? "bg-amber-500 text-zinc-950" : "text-zinc-400 hover:text-zinc-200"}`}
            >
              Single Render
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("batch");
                setUseFileVray(true);
                if (namedViews.length > 0) setCameraChoice(`rhino:${namedViews[0]}`);
                else setCameraChoice("file_active");
              }}
              className={`flex-1 rounded-md py-1.5 text-xs font-medium ${mode === "batch" ? "bg-amber-500 text-zinc-950" : "text-zinc-400 hover:text-zinc-200"}`}
            >
              Batch SKU × Finish Queue
            </button>
          </div>

          {/* Camera & Resolution */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">Camera View</label>
              <select value={cameraChoice} onChange={(e) => setCameraChoice(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60">
                <option value="file_active">Keep Rhino file&apos;s saved active view</option>
                {namedViews.length > 0 && (
                  <optgroup label="Rhino Named Views (from file)">
                    {namedViews.map((nv) => (
                      <option key={`rhino:${nv}`} value={`rhino:${nv}`}>{nv}</option>
                    ))}
                  </optgroup>
                )}
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
                <optgroup label="Standard projections (auto-fit)">
                  <option value="iso">Perspective (auto-fit)</option>
                  <option value="front">Front elevation</option>
                  <option value="top">Top / plan</option>
                </optgroup>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">V-Ray Resolution</label>
              <label className="mb-2 flex items-center gap-2 text-xs text-zinc-300">
                <input type="checkbox" checked={useFileVray} onChange={(e) => setUseFileVray(e.target.checked)} />
                Use V-Ray output resolution saved in Rhino file
              </label>
              {!useFileVray && (
                <div className="flex flex-wrap gap-1.5">
                  {RESOLUTIONS.map((r) => (
                    <button key={r.label} type="button" onClick={() => { setW(r.w); setH(r.h); }}
                      className={`rounded border px-2 py-1 text-[11px] ${w === r.w && h === r.h ? "border-amber-500/60 bg-amber-500/10 text-amber-300" : "border-zinc-700 text-zinc-400 hover:border-zinc-500"}`}>
                      {r.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {mode === "batch" && (
            <div className="space-y-4 border-t border-zinc-800 pt-4">
              {/* 1. Output directory */}
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-zinc-500">
                  1. Output Folder (creates a subfolder per SKU layer)
                </label>
                <div className="flex gap-2">
                  <input
                    value={outputDir}
                    onChange={(e) => setOutputDir(e.target.value)}
                    placeholder="C:\Users\Skutchi\Documents\Renders"
                    className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60"
                  />
                  <button
                    type="button"
                    onClick={browseFolder}
                    className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs font-medium text-zinc-200 hover:bg-zinc-800"
                  >
                    Browse…
                  </button>
                </div>
              </div>

              {/* 2. SKU Layers */}
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <label className="text-xs uppercase tracking-wide text-zinc-500">
                    2. SKU Layers to Render ({selectedSkus.size} of {availableSkus.length} selected)
                  </label>
                  <div className="flex gap-2 text-xs">
                    <button type="button" onClick={() => setSelectedSkus(new Set(availableSkus))} className="text-amber-400 hover:underline">Select all</button>
                    <button type="button" onClick={() => setSelectedSkus(new Set())} className="text-zinc-500 hover:underline">Clear</button>
                  </div>
                </div>
                <div className="grid max-h-36 grid-cols-2 gap-1.5 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 p-2 sm:grid-cols-3">
                  {availableSkus.map((skuName) => {
                    const checked = selectedSkus.has(skuName);
                    return (
                      <label key={skuName} className={`flex cursor-pointer items-center gap-2 rounded border px-2 py-1.5 text-xs ${checked ? "border-amber-500/40 bg-amber-500/10 text-zinc-100" : "border-zinc-800 text-zinc-400"}`}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) => {
                            const next = new Set(selectedSkus);
                            if (e.target.checked) next.add(skuName);
                            else next.delete(skuName);
                            setSelectedSkus(next);
                          }}
                        />
                        <span className="truncate" title={skuName}>{skuName}</span>
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* 3. Varying part layer & queued finishes */}
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">
                    3. Part Layer(s) that Change Between Renders
                  </label>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <select
                      value={varyingLayer}
                      onChange={(e) => setVaryingLayer(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-amber-500/60"
                    >
                      {partLayers.map((l) => (
                        <option key={l.name} value={l.name}>Primary: {l.name} ({l.part_count})</option>
                      ))}
                    </select>
                    <select
                      value={secondVaryingLayer}
                      onChange={(e) => setSecondVaryingLayer(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-400 outline-none focus:border-amber-500/60"
                    >
                      <option value="">+ 2nd varying layer (optional)</option>
                      {partLayers.filter((l) => l.name !== varyingLayer).map((l) => (
                        <option key={l.name} value={l.name}>2nd: {l.name} ({l.part_count})</option>
                      ))}
                    </select>
                  </div>
                  <p className="mt-1.5 text-[11px] text-zinc-500">
                    Other assigned part layers stay fixed across all renders. Each PNG is named after the changing finish(es).
                  </p>

                  {/* Queued list with per-finish custom scale */}
                  <div className="mt-3">
                    <div className="mb-1 flex items-center justify-between text-xs text-zinc-400">
                      <span>Queued Finishes ({queuedFinishes.length})</span>
                      {queuedFinishes.length > 0 && (
                        <button type="button" onClick={() => setQueuedFinishes([])} className="text-[11px] text-zinc-500 hover:text-red-400">Clear queue</button>
                      )}
                    </div>
                    <div className="max-h-44 space-y-1.5 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 p-2">
                      {queuedFinishes.length === 0 && (
                        <p className="py-6 text-center text-xs text-zinc-600">Click finishes on the right to add them to the batch queue →</p>
                      )}
                      {queuedFinishes.map((qf, idx) => {
                        const fin = finishById.get(qf.finish_id);
                        if (!fin) return null;
                        return (
                          <div key={qf.finish_id} className="space-y-1 rounded border border-zinc-800 bg-zinc-900/70 px-2 py-1.5 text-xs">
                            <div className="flex items-center gap-2">
                              <span className="w-4 text-[10px] text-zinc-500">{idx + 1}.</span>
                              <img src={fin.thumb_url} alt="" className="h-6 w-6 rounded object-cover" />
                              <span className="min-w-0 flex-1 truncate text-zinc-200">{fin.name}</span>
                              <label className="flex items-center gap-1 text-[10px] text-zinc-400">
                                <span>×</span>
                                <input
                                  type="number"
                                  min="0.01"
                                  step="0.1"
                                  value={qf.scale_multiplier}
                                  onChange={(e) => updateQueuedScale(qf.finish_id, Number(e.target.value))}
                                  className="w-12 rounded border border-zinc-700 bg-zinc-950 px-1 py-0.5 text-amber-300"
                                />
                              </label>
                              <button type="button" onClick={() => toggleQueuedFinish(fin)} className="text-zinc-500 hover:text-red-400">✕</button>
                            </div>
                            {secondVaryingLayer && (
                              <div className="flex items-center gap-2 pl-6 text-[11px]">
                                <span className="text-zinc-500">{secondVaryingLayer}:</span>
                                <select
                                  value={qf.extra_finish_id || ""}
                                  onChange={(e) => {
                                    const val = e.target.value ? Number(e.target.value) : null;
                                    setQueuedFinishes((prev) => prev.map((x) => (x.finish_id === qf.finish_id ? { ...x, extra_finish_id: val, extra_scale: x.extra_scale || 1 } : x)));
                                  }}
                                  className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-0.5 text-zinc-300"
                                >
                                  <option value="">(keep base finish)</option>
                                  {(allFinishes || []).map((ef) => (
                                    <option key={ef.id} value={ef.id}>{ef.name}</option>
                                  ))}
                                </select>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>

                {/* Finish library selector */}
                <div>
                  <div className="mb-1.5 flex items-center justify-between">
                    <label className="text-xs uppercase tracking-wide text-zinc-500">
                      4. Pick Finishes to Queue
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        const existingIds = new Set(queuedFinishes.map((x) => x.finish_id));
                        const existingAssign = assignments.find((a) => a.target_kind === "layer" && a.target_name === varyingLayer);
                        const defaultScale = existingAssign?.scale_multiplier || 1;
                        const added = filteredFinishes
                          .filter((f) => !existingIds.has(f.id))
                          .map((f) => ({ finish_id: f.id, scale_multiplier: defaultScale }));
                        setQueuedFinishes([...queuedFinishes, ...added]);
                      }}
                      className="text-xs text-amber-400 hover:underline"
                    >
                      + Queue all shown ({filteredFinishes.length})
                    </button>
                  </div>
                  <div className="mb-2 flex flex-wrap items-center gap-1">
                    {(["all", "laminate", "pet", "product_finish", "other"] as const).map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => setFinishFilterCat(c)}
                        className={`rounded-full border px-2 py-0.5 text-[10px] ${finishFilterCat === c ? "border-amber-500/50 bg-amber-500/15 text-amber-300" : "border-zinc-700 text-zinc-400"}`}
                      >
                        {c === "all" ? "All" : CATEGORY_LABEL[c]}
                      </button>
                    ))}
                    <input
                      value={finishSearch}
                      onChange={(e) => setFinishSearch(e.target.value)}
                      placeholder="Filter…"
                      className="ml-auto w-28 rounded border border-zinc-700 bg-zinc-950 px-2 py-0.5 text-xs text-zinc-200 outline-none"
                    />
                  </div>
                  <div className="grid max-h-56 grid-cols-2 gap-1.5 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 p-2">
                    {filteredFinishes.map((f) => {
                      const isQueued = queuedFinishes.some((x) => x.finish_id === f.id);
                      return (
                        <button
                          key={f.id}
                          type="button"
                          onClick={() => toggleQueuedFinish(f)}
                          className={`flex items-center gap-2 rounded-lg border p-1.5 text-left text-xs ${isQueued ? "border-amber-500/60 bg-amber-500/15 text-amber-200" : "border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:border-zinc-700"}`}
                        >
                          <img src={f.thumb_url} alt="" className="h-8 w-8 shrink-0 rounded object-cover" />
                          <div className="min-w-0 flex-1">
                            <div className="truncate font-medium">{f.name}</div>
                            <div className="text-[10px] text-zinc-500">{f.swatch_width_in}×{f.swatch_height_in}&quot;</div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Batch output preview */}
              <div className="rounded-lg border border-amber-700/40 bg-amber-950/15 px-3 py-2 text-xs text-amber-200">
                <div>
                  <strong>Batch summary:</strong> {selectedSkus.size} SKU layer(s) × {queuedFinishes.length} finish(es) = <strong>{selectedSkus.size * queuedFinishes.length} PNG renders</strong>
                </div>
                <div className="mt-0.5 text-[11px] text-amber-300/80">
                  Output path pattern: <code>{outputDir || "<Output Folder>"}\&lt;SKU Layer&gt;\&lt;Finish Name&gt;.png</code>
                </div>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800">Cancel</button>
            <button onClick={submit} disabled={busy || !system}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:opacity-50">
              {busy ? "Queueing…" : mode === "batch" ? `Start Batch (${selectedSkus.size * queuedFinishes.length} renders)` : "Queue render"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
