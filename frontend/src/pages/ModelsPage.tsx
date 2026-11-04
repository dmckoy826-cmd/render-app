import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtDate, toast } from "../api";
import { usePoll } from "../hooks";
import { StatusChip } from "../components/JobProgress";
import type { ModelSummary } from "../types";

export function SourceBadge({ analyzer, className = "" }: { analyzer: string; className?: string }) {
  const a = analyzer || "";
  const true_ = a.startsWith("dxf") || a.startsWith("rhino");
  return (
    <span className={`rounded border px-1.5 py-0.5 text-[10px] ${true_
      ? "border-emerald-600/40 bg-emerald-950/85 text-emerald-300"
      : "border-amber-600/40 bg-amber-950/85 text-amber-300"} ${className}`}>
      {a.startsWith("dxf") ? "DXF · true geometry" : a.startsWith("rhino") ? "RHINO · true geometry" : "SIM · placeholder structure"}
    </span>
  );
}

export default function ModelsPage() {
  const nav = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const { data, refresh } = usePoll<ModelSummary[]>(() => api.get("/api/models"), 2500);

  const onFile = async (f: File) => {
    setUploading(true);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api.upload("/api/models", fd);
      toast(`Uploaded ${r.model.name} — analyzing structure…`);
      refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : "upload failed", "err");
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  return (
    <div className="mx-auto max-w-7xl px-8 py-8">
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">Models</h1>
          <p className="mt-1 text-sm text-zinc-500">
            Upload DWG / DXF / 3DM / SKP / STEP files — layers, blocks and parts are extracted for finish mapping.
          </p>
        </div>
        <input ref={fileRef} type="file" hidden accept=".dwg,.dxf,.3dm,.skp,.obj,.fbx,.step,.stp,.iges,.igs,.sat,.stl,.3ds,.ifc"
          onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
        <button onClick={() => fileRef.current?.click()} disabled={uploading}
          className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400 disabled:opacity-50">
          {uploading ? "Uploading…" : "Upload model"}
        </button>
      </header>

      {!data && <p className="py-20 text-center text-sm text-zinc-500">Loading…</p>}
      {data && data.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-800 py-24 text-center">
          <p className="text-sm text-zinc-400">No models yet.</p>
          <p className="mt-1 text-xs text-zinc-600">Upload a DWG (or anything AutoCAD/Rhino exports) to get started.</p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        {(data || []).map((m) => (
          <button key={m.id} onClick={() => nav(`/models/${m.id}`)}
            className="group overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50 text-left transition-colors hover:border-amber-500/50">
            <div className="relative flex h-44 items-center justify-center overflow-hidden bg-zinc-950">
              {m.preview_url
                ? <img src={m.preview_url} alt={m.name} className="h-full w-full object-contain transition-transform group-hover:scale-[1.03]" />
                : <svg viewBox="0 0 24 24" className="h-10 w-10 text-zinc-700" fill="currentColor"><path d="M12 2 3 7v10l9 5 9-5V7l-9-5Z" /></svg>}
              <SourceBadge analyzer={m.analyzer} className="absolute left-2 top-2" />
            </div>
            <div className="border-t border-zinc-800 p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-zinc-200">{m.name}</span>
                <StatusChip status={m.status} />
              </div>
              <div className="mt-1 truncate text-xs text-zinc-500">{m.original_name}</div>
              <div className="mt-3 flex items-center gap-3 text-[11px] text-zinc-500">
                <span>{m.layer_count} layers</span>
                <span className="text-zinc-700">·</span>
                <span>{m.block_count} blocks</span>
                <span className="text-zinc-700">·</span>
                <span>{m.part_count} parts</span>
                <span className="ml-auto">{fmtDate(m.created_at)}</span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
