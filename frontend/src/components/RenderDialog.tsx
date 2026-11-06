import { useEffect, useMemo, useState } from "react";
import Modal from "./Modal";
import JobProgress from "./JobProgress";
import FinishSettingsModal, {
  formatTransformSummary,
  type FinishTransformSettings,
} from "./FinishSettingsModal";
import { api, toast } from "../api";
import {
  CATEGORY_LABEL,
  type Assignment,
  type BlockInfo,
  type CameraPose,
  type Category,
  type Finish,
  type Job,
  type LayerInfo,
  type Part,
  type SavedCameraView,
  type SkuLayerInfo,
  type SystemInfo,
} from "../types";
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
  rotation_deg: number;
  offset_u_in: number;
  offset_v_in: number;
  extra_finish_id?: number | null;
  extra_scale?: number;
  extra_rotation_deg?: number;
  extra_offset_u_in?: number;
  extra_offset_v_in?: number;
}

function parseTargetSpec(spec: string): {
  kind: "layer" | "block" | "part";
  name: string;
} | null {
  if (!spec) return null;
  const idx = spec.indexOf(":");
  if (idx < 0) return { kind: "layer", name: spec };
  const prefix = spec.slice(0, idx);
  const name = spec.slice(idx + 1);
  if (prefix === "layer" || prefix === "block" || prefix === "part") {
    return { kind: prefix, name };
  }
  return { kind: "layer", name: spec };
}

export default function RenderDialog({
  open,
  onClose,
  modelId,
  onDone,
  initialMode = "single",
  currentCameraPose,
  savedViews = [],
  namedViews = [],
  skuLayers = [],
  partLayers = [],
  blocks = [],
  parts = [],
  targetSchema,
  assignments = [],
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
  blocks?: BlockInfo[];
  parts?: Part[];
  targetSchema?: string;
  assignments?: Assignment[];
}) {
  const [mode, setMode] = useState<"single" | "batch">(initialMode);
  const [w, setW] = useState(1920);
  const [h, setH] = useState(1080);
  const [useFileVray, setUseFileVray] = useState(false);
  const [vrayDevice, setVrayDevice] = useState<string>("rtx");
  const [vraySpeed, setVraySpeed] = useState<string>("fast");
  const [quality, setQuality] = useState<"draft" | "standard" | "high">("standard");
  const [cameraChoice, setCameraChoice] = useState<string>("viewer");
  const [singleIsolateSku, setSingleIsolateSku] = useState<string>("");
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);

  // Batch state
  const [outputDir, setOutputDir] = useState<string>(() => {
    try {
      return localStorage.getItem(OUT_DIR_STORAGE_KEY) || "";
    } catch {
      return "";
    }
  });
  const [selectedSkus, setSelectedSkus] = useState<Set<string>>(new Set());
  const [varyingTarget, setVaryingTarget] = useState<string>("");
  const [secondVaryingTarget, setSecondVaryingTarget] = useState<string>("");
  const [queuedFinishes, setQueuedFinishes] = useState<QueuedFinishItem[]>([]);
  const [finishFilterCat, setFinishFilterCat] = useState<"all" | Category>("all");
  const [finishSearch, setFinishSearch] = useState("");
  const [editingTransform, setEditingTransform] = useState<{
    finishId: number;
    slot: "primary" | "secondary";
    targetLabel: string;
    finish: Finish;
    initial: FinishTransformSettings;
  } | null>(null);

  const { data: system } = usePoll<SystemInfo>(() => api.get("/api/system/info"), 5000, open);
  const { data: allFinishes } = usePoll<Finish[]>(() => api.get("/api/finishes"), 30000, open);
  const realWorker = system?.runner === "agent";

  // Candidate SKU layers: use structure.sku_layers if present, otherwise fallback to partLayers
  const availableSkus = useMemo(() => {
    if (skuLayers.length > 0) return skuLayers.map((s) => s.name);
    return partLayers.map((l) => l.name);
  }, [skuLayers, partLayers]);

  const partTargetKey = (p: Part) =>
    targetSchema === "rhino-geometry-v1" ? p.id : p.name;

  // Target options that can switch between renders (Layers, Blocks, and assigned/renderable Parts)
  const switchableTargets = useMemo(() => {
    const list: { spec: string; kind: "layer" | "block" | "part"; name: string; label: string }[] = [];
    for (const l of partLayers) {
      list.push({
        spec: `layer:${l.name}`,
        kind: "layer",
        name: l.name,
        label: `Layer: ${l.name} (${l.part_count} parts)`,
      });
    }
    for (const b of blocks) {
      list.push({
        spec: `block:${b.name}`,
        kind: "block",
        name: b.name,
        label: `Block: ${b.name} (×${b.instance_count})`,
      });
    }
    // Include parts that already have an override or first 100 renderable parts
    const assignedPartKeys = new Set(
      assignments.filter((a) => a.target_kind === "part").map((a) => a.target_name)
    );
    const candidateParts = parts
      .filter((p) => p.renderable !== false && (assignedPartKeys.has(partTargetKey(p)) || parts.length <= 150))
      .slice(0, 100);
    for (const p of candidateParts) {
      const tName = partTargetKey(p);
      list.push({
        spec: `part:${tName}`,
        kind: "part",
        name: tName,
        label: `Part: ${p.name} (${p.layer})`,
      });
    }
    return list;
  }, [partLayers, blocks, parts, assignments, targetSchema]);

  useEffect(() => {
    if (!open) {
      setJob(null);
      setBusy(false);
      return;
    }
    setMode(initialMode);
    setJob(null);
    setBusy(false);
    setSelectedSkus(new Set(availableSkus));
    if (switchableTargets.length > 0) {
      setVaryingTarget((prev) =>
        prev && switchableTargets.some((t) => t.spec === prev)
          ? prev
          : switchableTargets[0].spec
      );
    }
    if (initialMode === "batch") {
      setUseFileVray(true);
      if (namedViews.length > 0) setCameraChoice(`rhino:${namedViews[0]}`);
      else setCameraChoice("file_active");
    } else if (currentCameraPose) {
      setCameraChoice("viewer");
    }
  }, [open, initialMode]); // eslint-disable-line react-hooks/exhaustive-deps

  const active = job && !["done", "failed", "canceled"].includes(job.status);

  useEffect(() => {
    if (!job || !active) return;
    const t = setInterval(async () => {
      try {
        const j = await api.get(`/api/jobs/${job.id}`);
        setJob(j);
        if (j.status === "done") {
          const count = j.settings?.saved_files?.length;
          toast(
            count
              ? `Batch finished — saved ${count} PNGs to ${j.settings?.output_dir}`
              : "Render finished — see Renders tab"
          );
          onDone();
        }
        if (j.status === "failed") toast(`Render failed: ${j.error}`, "err");
      } catch {
        /* ignore */
      }
    }, 1200);
    return () => clearInterval(t);
  }, [job?.id, active]); // eslint-disable-line react-hooks/exhaustive-deps

  const browseFolder = async () => {
    try {
      const res = await api.get("/api/system/pick-folder");
      if (res?.path) {
        setOutputDir(res.path);
        try {
          localStorage.setItem(OUT_DIR_STORAGE_KEY, res.path);
        } catch {
          /* ignore */
        }
      }
    } catch {
      toast("Could not open folder picker — paste folder path directly", "err");
    }
  };

  const defaultTransformForTarget = (spec: string): FinishTransformSettings => {
    const parsed = parseTargetSpec(spec);
    if (!parsed) {
      return { scale_multiplier: 1, rotation_deg: 0, offset_u_in: 0, offset_v_in: 0 };
    }
    const existing = assignments.find(
      (a) => a.target_kind === parsed.kind && a.target_name === parsed.name
    );
    return {
      scale_multiplier: existing?.scale_multiplier || 1,
      rotation_deg: existing?.rotation_deg || 0,
      offset_u_in: existing?.offset_u_in || 0,
      offset_v_in: existing?.offset_v_in || 0,
    };
  };

  const toggleQueuedFinish = (f: Finish) => {
    setQueuedFinishes((prev) => {
      const exists = prev.find((x) => x.finish_id === f.id);
      if (exists) return prev.filter((x) => x.finish_id !== f.id);
      const defaults = defaultTransformForTarget(varyingTarget);
      return [
        ...prev,
        {
          finish_id: f.id,
          scale_multiplier: defaults.scale_multiplier,
          rotation_deg: defaults.rotation_deg,
          offset_u_in: defaults.offset_u_in,
          offset_v_in: defaults.offset_v_in,
        },
      ];
    });
  };

  const filteredFinishes = useMemo(() => {
    return (allFinishes || []).filter(
      (f) =>
        (finishFilterCat === "all" || f.category === finishFilterCat) &&
        (!finishSearch ||
          `${f.name} ${f.tags}`.toLowerCase().includes(finishSearch.toLowerCase()))
    );
  }, [allFinishes, finishFilterCat, finishSearch]);

  const finishById = useMemo(
    () => new Map((allFinishes || []).map((f) => [f.id, f])),
    [allFinishes]
  );

  const primaryParsed = parseTargetSpec(varyingTarget);
  const secondaryParsed = parseTargetSpec(secondVaryingTarget);

  const fixedBaseAssignments = useMemo(() => {
    return assignments.filter((a) => {
      if (!a.finish_id) return false;
      if (
        primaryParsed &&
        a.target_kind === primaryParsed.kind &&
        a.target_name === primaryParsed.name
      ) {
        return false;
      }
      if (
        secondaryParsed &&
        a.target_kind === secondaryParsed.kind &&
        a.target_name === secondaryParsed.name
      ) {
        return false;
      }
      return true;
    });
  }, [assignments, primaryParsed, secondaryParsed]);

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
      } else if (
        cameraChoice === "front" ||
        cameraChoice === "top" ||
        cameraChoice === "iso"
      ) {
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
        if (!primaryParsed) {
          toast("Select the target (layer, block, or part) that switches between renders", "err");
          setBusy(false);
          return;
        }
        if (!queuedFinishes.length) {
          toast("Queue at least one finish variation to render", "err");
          setBusy(false);
          return;
        }
        try {
          localStorage.setItem(OUT_DIR_STORAGE_KEY, outputDir.trim());
        } catch {
          /* ignore */
        }

        const base_assignments = fixedBaseAssignments.map((a) => ({
          target_kind: a.target_kind,
          target_name: a.target_name,
          finish_id: a.finish_id,
          scale_multiplier: a.scale_multiplier || 1,
          rotation_deg: a.rotation_deg || 0,
          offset_u_in: a.offset_u_in || 0,
          offset_v_in: a.offset_v_in || 0,
        }));

        const variations = queuedFinishes.map((qf) => {
          const fin = finishById.get(qf.finish_id);
          const extraFin =
            secondaryParsed && qf.extra_finish_id
              ? finishById.get(qf.extra_finish_id)
              : undefined;
          const labelParts = [fin?.name || `Finish_${qf.finish_id}`];
          const overrides: Record<string, any>[] = [
            {
              target_kind: primaryParsed.kind,
              target_name: primaryParsed.name,
              finish_id: qf.finish_id,
              scale_multiplier: qf.scale_multiplier || 1,
              rotation_deg: qf.rotation_deg || 0,
              offset_u_in: qf.offset_u_in || 0,
              offset_v_in: qf.offset_v_in || 0,
            },
          ];
          if (secondaryParsed && extraFin) {
            labelParts.push(extraFin.name);
            overrides.push({
              target_kind: secondaryParsed.kind,
              target_name: secondaryParsed.name,
              finish_id: extraFin.id,
              scale_multiplier: qf.extra_scale || 1,
              rotation_deg: qf.extra_rotation_deg || 0,
              offset_u_in: qf.extra_offset_u_in || 0,
              offset_v_in: qf.extra_offset_v_in || 0,
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
          vray_device: vrayDevice,
          vray_speed: vraySpeed,
          ...(mode === "single" && singleIsolateSku
            ? { isolate_sku_layer: singleIsolateSku }
            : {}),
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
    <Modal
      open={open}
      onClose={onClose}
      title={
        mode === "batch"
          ? "Batch SKU × Finish Queue Render"
          : realWorker
          ? "Render via worker"
          : "Simulated render"
      }
      wide={mode === "batch"}
    >
      {job && active ? (
        <JobProgress
          job={job}
          onCanceled={() => {
            setJob(null);
            setBusy(false);
          }}
        />
      ) : (
        <div className="space-y-4">
          {/* Mode selector */}
          <div className="flex rounded-lg border border-zinc-800 bg-zinc-950 p-1">
            <button
              type="button"
              onClick={() => setMode("single")}
              className={`flex-1 rounded-md py-1.5 text-xs font-medium ${
                mode === "single"
                  ? "bg-amber-500 text-zinc-950"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
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
              className={`flex-1 rounded-md py-1.5 text-xs font-medium ${
                mode === "batch"
                  ? "bg-amber-500 text-zinc-950"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Batch SKU × Finish Queue
            </button>
          </div>

          {/* Camera & Resolution */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">
                Camera View
              </label>
              <select
                value={cameraChoice}
                onChange={(e) => setCameraChoice(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60"
              >
                <option value="file_active">
                  Keep Rhino file&apos;s saved active view
                </option>
                {namedViews.length > 0 && (
                  <optgroup label="Rhino Named Views (from file)">
                    {namedViews.map((nv) => (
                      <option key={`rhino:${nv}`} value={`rhino:${nv}`}>
                        {nv}
                      </option>
                    ))}
                  </optgroup>
                )}
                {currentCameraPose && (
                  <option value="viewer">Current 3D viewer angle</option>
                )}
                {savedViews.length > 0 && (
                  <optgroup label="Saved UI views">
                    {savedViews.map((sv) => (
                      <option key={`saved:${sv.name}`} value={`saved:${sv.name}`}>
                        {sv.name}
                      </option>
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
              <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">
                V-Ray Resolution
              </label>
              <label className="mb-2 flex items-center gap-2 text-xs text-zinc-300">
                <input
                  type="checkbox"
                  checked={useFileVray}
                  onChange={(e) => setUseFileVray(e.target.checked)}
                />
                Use V-Ray output resolution saved in Rhino file
              </label>
              {!useFileVray && (
                <div className="flex flex-wrap gap-1.5">
                  {RESOLUTIONS.map((r) => (
                    <button
                      key={r.label}
                      type="button"
                      onClick={() => {
                        setW(r.w);
                        setH(r.h);
                      }}
                      className={`rounded border px-2 py-1 text-[11px] ${
                        w === r.w && h === r.h
                          ? "border-amber-500/60 bg-amber-500/10 text-amber-300"
                          : "border-zinc-700 text-zinc-400 hover:border-zinc-500"
                      }`}
                    >
                      {r.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* V-Ray API Hardware Acceleration & Speed Controls */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">
                V-Ray Render Engine (API)
              </label>
              <select
                value={vrayDevice}
                onChange={(e) => setVrayDevice(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-amber-500/60"
              >
                <option value="rtx">NVIDIA RTX (Fastest GPU Raytracing)</option>
                <option value="cuda">GPU CUDA / Hybrid (GPU + CPU)</option>
                <option value="cpu">CPU Only</option>
                <option value="file">Keep Engine Saved in Rhino File</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">
                V-Ray Speed / Noise Limit (API)
              </label>
              <select
                value={vraySpeed}
                onChange={(e) => setVraySpeed(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-amber-500/60"
              >
                <option value="turbo">Turbo Preview (~15s cap · Noise 0.05)</option>
                <option value="fast">Fast Production (~45s cap · Noise 0.025)</option>
                <option value="balanced">Balanced Quality (~90s cap · Noise 0.015)</option>
                <option value="high">High Quality (~3m cap · Noise 0.008)</option>
                <option value="file">Keep Noise / Time Settings from Rhino File</option>
              </select>
            </div>
          </div>

          {/* Single-render SKU isolation selector */}
          {mode === "single" && availableSkus.length > 1 && (
            <div>
              <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">
                SKU Layer Isolation (turn off other SKU layers)
              </label>
              <select
                value={singleIsolateSku}
                onChange={(e) => setSingleIsolateSku(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-amber-500/60"
              >
                <option value="">All visible layers (as saved in file)</option>
                {availableSkus.map((skuName) => (
                  <option key={skuName} value={skuName}>
                    Isolate SKU Layer: {skuName} (turn off all other SKU layers)
                  </option>
                ))}
              </select>
            </div>
          )}

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
                    2. SKU Layers to Isolate & Render ({selectedSkus.size} of{" "}
                    {availableSkus.length} selected — turns OFF all other SKU layers per render)
                  </label>
                  <div className="flex gap-2 text-xs">
                    <button
                      type="button"
                      onClick={() => setSelectedSkus(new Set(availableSkus))}
                      className="text-amber-400 hover:underline"
                    >
                      Select all
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedSkus(new Set())}
                      className="text-zinc-500 hover:underline"
                    >
                      Clear
                    </button>
                  </div>
                </div>
                <div className="grid max-h-36 grid-cols-2 gap-1.5 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 p-2 sm:grid-cols-3">
                  {availableSkus.map((skuName) => {
                    const checked = selectedSkus.has(skuName);
                    return (
                      <label
                        key={skuName}
                        className={`flex cursor-pointer items-center gap-2 rounded border px-2 py-1.5 text-xs ${
                          checked
                            ? "border-amber-500/40 bg-amber-500/10 text-zinc-100"
                            : "border-zinc-800 text-zinc-400"
                        }`}
                      >
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
                        <span className="truncate" title={skuName}>
                          {skuName}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>

              {/* 3. Varying target & queued finishes */}
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div>
                  <label className="mb-1.5 block text-xs uppercase tracking-wide text-zinc-500">
                    3. Target(s) (Layer, Block, or Part) to Switch Between Renders
                  </label>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <select
                      value={varyingTarget}
                      onChange={(e) => setVaryingTarget(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-200 outline-none focus:border-amber-500/60"
                    >
                      {switchableTargets.map((t) => (
                        <option key={t.spec} value={t.spec}>
                          Primary: {t.label}
                        </option>
                      ))}
                    </select>
                    <select
                      value={secondVaryingTarget}
                      onChange={(e) => setSecondVaryingTarget(e.target.value)}
                      className="w-full rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-2 text-xs text-zinc-400 outline-none focus:border-amber-500/60"
                    >
                      <option value="">+ 2nd switching target (optional)</option>
                      {switchableTargets
                        .filter((t) => t.spec !== varyingTarget)
                        .map((t) => (
                          <option key={t.spec} value={t.spec}>
                            2nd: {t.label}
                          </option>
                        ))}
                    </select>
                  </div>
                  <p className="mt-1.5 text-[11px] text-zinc-500">
                    Fixed across all renders:{" "}
                    {fixedBaseAssignments.length > 0 ? (
                      <span className="text-zinc-300">
                        {fixedBaseAssignments
                          .map(
                            (a) =>
                              `${a.target_name} (${a.finish?.name || `#${a.finish_id}`})`
                          )
                          .join(", ")}
                      </span>
                    ) : (
                      <span>none (assign base finishes in the workspace first)</span>
                    )}
                    .
                  </p>

                  {/* Queued list with button to open Scale / Rotate / Offset modal */}
                  <div className="mt-3">
                    <div className="mb-1 flex items-center justify-between text-xs text-zinc-400">
                      <span>Queued Finish Variations ({queuedFinishes.length})</span>
                      {queuedFinishes.length > 0 && (
                        <button
                          type="button"
                          onClick={() => setQueuedFinishes([])}
                          className="text-[11px] text-zinc-500 hover:text-red-400"
                        >
                          Clear queue
                        </button>
                      )}
                    </div>
                    <div className="max-h-48 space-y-1.5 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950 p-2">
                      {queuedFinishes.length === 0 && (
                        <p className="py-6 text-center text-xs text-zinc-600">
                          Click finishes on the right to add them to the render queue →
                        </p>
                      )}
                      {queuedFinishes.map((qf, idx) => {
                        const fin = finishById.get(qf.finish_id);
                        if (!fin) return null;
                        const extraFin =
                          secondVaryingTarget && qf.extra_finish_id
                            ? finishById.get(qf.extra_finish_id)
                            : undefined;
                        return (
                          <div
                            key={qf.finish_id}
                            className="space-y-1.5 rounded border border-zinc-800 bg-zinc-900/70 px-2.5 py-2 text-xs"
                          >
                            <div className="flex items-center gap-2">
                              <span className="w-4 text-[10px] text-zinc-500">
                                {idx + 1}.
                              </span>
                              <img
                                src={fin.thumb_url}
                                alt=""
                                className="h-6 w-6 rounded object-cover"
                              />
                              <span className="min-w-0 flex-1 truncate text-zinc-200 font-medium">
                                {fin.name}
                              </span>
                              <button
                                type="button"
                                onClick={() =>
                                  setEditingTransform({
                                    finishId: qf.finish_id,
                                    slot: "primary",
                                    targetLabel:
                                      primaryParsed?.name || "Primary Target",
                                    finish: fin,
                                    initial: {
                                      scale_multiplier: qf.scale_multiplier || 1,
                                      rotation_deg: qf.rotation_deg || 0,
                                      offset_u_in: qf.offset_u_in || 0,
                                      offset_v_in: qf.offset_v_in || 0,
                                    },
                                  })
                                }
                                className="inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[11px] font-mono text-amber-300 hover:bg-amber-500/20"
                                title="Adjust Scale, Rotation (0–90°), and Seam Offset"
                              >
                                <span>⚙</span>
                                {formatTransformSummary({
                                  scale_multiplier: qf.scale_multiplier,
                                  rotation_deg: qf.rotation_deg,
                                  offset_u_in: qf.offset_u_in,
                                  offset_v_in: qf.offset_v_in,
                                })}
                              </button>
                              <button
                                type="button"
                                onClick={() => toggleQueuedFinish(fin)}
                                className="text-zinc-500 hover:text-red-400"
                              >
                                ✕
                              </button>
                            </div>
                            {secondVaryingTarget && secondaryParsed && (
                              <div className="flex items-center gap-2 pl-6 text-[11px]">
                                <span className="text-zinc-500 truncate max-w-[110px]">
                                  {secondaryParsed.name}:
                                </span>
                                <select
                                  value={qf.extra_finish_id || ""}
                                  onChange={(e) => {
                                    const val = e.target.value
                                      ? Number(e.target.value)
                                      : null;
                                    const secDef =
                                      defaultTransformForTarget(secondVaryingTarget);
                                    setQueuedFinishes((prev) =>
                                      prev.map((x) =>
                                        x.finish_id === qf.finish_id
                                          ? {
                                              ...x,
                                              extra_finish_id: val,
                                              extra_scale:
                                                x.extra_scale ||
                                                secDef.scale_multiplier,
                                              extra_rotation_deg:
                                                x.extra_rotation_deg ??
                                                secDef.rotation_deg,
                                              extra_offset_u_in:
                                                x.extra_offset_u_in ??
                                                secDef.offset_u_in,
                                              extra_offset_v_in:
                                                x.extra_offset_v_in ??
                                                secDef.offset_v_in,
                                            }
                                          : x
                                      )
                                    );
                                  }}
                                  className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-950 px-1.5 py-0.5 text-zinc-300"
                                >
                                  <option value="">(keep base finish)</option>
                                  {(allFinishes || []).map((ef) => (
                                    <option key={ef.id} value={ef.id}>
                                      {ef.name}
                                    </option>
                                  ))}
                                </select>
                                {extraFin && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setEditingTransform({
                                        finishId: qf.finish_id,
                                        slot: "secondary",
                                        targetLabel: secondaryParsed.name,
                                        finish: extraFin,
                                        initial: {
                                          scale_multiplier: qf.extra_scale || 1,
                                          rotation_deg: qf.extra_rotation_deg || 0,
                                          offset_u_in: qf.extra_offset_u_in || 0,
                                          offset_v_in: qf.extra_offset_v_in || 0,
                                        },
                                      })
                                    }
                                    className="inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-mono text-amber-300 hover:bg-amber-500/20"
                                  >
                                    <span>⚙</span>
                                    {formatTransformSummary({
                                      scale_multiplier: qf.extra_scale || 1,
                                      rotation_deg: qf.extra_rotation_deg || 0,
                                      offset_u_in: qf.extra_offset_u_in || 0,
                                      offset_v_in: qf.extra_offset_v_in || 0,
                                    })}
                                  </button>
                                )}
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
                        const existingIds = new Set(
                          queuedFinishes.map((x) => x.finish_id)
                        );
                        const defaults = defaultTransformForTarget(varyingTarget);
                        const added = filteredFinishes
                          .filter((f) => !existingIds.has(f.id))
                          .map((f) => ({
                            finish_id: f.id,
                            scale_multiplier: defaults.scale_multiplier,
                            rotation_deg: defaults.rotation_deg,
                            offset_u_in: defaults.offset_u_in,
                            offset_v_in: defaults.offset_v_in,
                          }));
                        setQueuedFinishes([...queuedFinishes, ...added]);
                      }}
                      className="text-xs text-amber-400 hover:underline"
                    >
                      + Queue all shown ({filteredFinishes.length})
                    </button>
                  </div>
                  <div className="mb-2 flex flex-wrap items-center gap-1">
                    {(
                      ["all", "laminate", "pet", "product_finish", "other"] as const
                    ).map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => setFinishFilterCat(c)}
                        className={`rounded-full border px-2 py-0.5 text-[10px] ${
                          finishFilterCat === c
                            ? "border-amber-500/50 bg-amber-500/15 text-amber-300"
                            : "border-zinc-700 text-zinc-400"
                        }`}
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
                      const isQueued = queuedFinishes.some(
                        (x) => x.finish_id === f.id
                      );
                      return (
                        <button
                          key={f.id}
                          type="button"
                          onClick={() => toggleQueuedFinish(f)}
                          className={`flex items-center gap-2 rounded-lg border p-1.5 text-left text-xs ${
                            isQueued
                              ? "border-amber-500/60 bg-amber-500/15 text-amber-200"
                              : "border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:border-zinc-700"
                          }`}
                        >
                          <img
                            src={f.thumb_url}
                            alt=""
                            className="h-8 w-8 shrink-0 rounded object-cover"
                          />
                          <div className="min-w-0 flex-1">
                            <div className="truncate font-medium">{f.name}</div>
                            <div className="text-[10px] text-zinc-500">
                              {f.swatch_width_in}×{f.swatch_height_in}&quot;
                            </div>
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
                  <strong>Batch summary:</strong> {selectedSkus.size} SKU layer(s) ×{" "}
                  {queuedFinishes.length} finish variation(s) ={" "}
                  <strong>
                    {selectedSkus.size * queuedFinishes.length} PNG renders
                  </strong>
                </div>
                <div className="mt-0.5 text-[11px] text-amber-300/80">
                  Output path pattern:{" "}
                  <code>
                    {outputDir || "<Output Folder>"}\&lt;SKU Layer&gt;\&lt;Finish
                    Name&gt;.png
                  </code>
                </div>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              onClick={onClose}
              className="rounded-lg border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-zinc-800"
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={busy || !system}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:opacity-50"
            >
              {busy
                ? "Queueing…"
                : mode === "batch"
                ? `Start Batch (${
                    selectedSkus.size * queuedFinishes.length
                  } renders)`
                : "Queue render"}
            </button>
          </div>
        </div>
      )}

      {editingTransform && (
        <FinishSettingsModal
          targetLabel={editingTransform.targetLabel}
          finish={editingTransform.finish}
          initial={editingTransform.initial}
          onClose={() => setEditingTransform(null)}
          onApply={(next) => {
            setQueuedFinishes((prev) =>
              prev.map((item) => {
                if (item.finish_id !== editingTransform.finishId) return item;
                if (editingTransform.slot === "primary") {
                  return {
                    ...item,
                    scale_multiplier: next.scale_multiplier,
                    rotation_deg: next.rotation_deg,
                    offset_u_in: next.offset_u_in,
                    offset_v_in: next.offset_v_in,
                  };
                }
                return {
                  ...item,
                  extra_scale: next.scale_multiplier,
                  extra_rotation_deg: next.rotation_deg,
                  extra_offset_u_in: next.offset_u_in,
                  extra_offset_v_in: next.offset_v_in,
                };
              })
            );
            setEditingTransform(null);
          }}
        />
      )}
    </Modal>
  );
}
