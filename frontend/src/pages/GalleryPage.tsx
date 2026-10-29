import { useState } from "react";
import { api, fmtDate, toast } from "../api";
import { usePoll } from "../hooks";
import Modal from "../components/Modal";
import type { RenderResult } from "../types";

export default function GalleryPage() {
  const { data, refresh } = usePoll<RenderResult[]>(() => api.get("/api/renders"), 5000);
  const [view, setView] = useState<RenderResult | null>(null);

  const remove = async (r: RenderResult) => {
    if (!window.confirm("Delete this render?")) return;
    await api.del(`/api/renders/${r.id}`);
    toast("Render deleted");
    refresh();
  };

  return (
    <div className="mx-auto max-w-7xl px-8 py-8">
      <header className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-100">Renders</h1>
        <p className="mt-1 text-sm text-zinc-500">Finished V-Ray outputs with the finish schedule used.</p>
      </header>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        {(data || []).map((r) => (
          <div key={r.id} className="group overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50">
            <button className="block w-full" onClick={() => setView(r)}>
              <img src={r.image_url} alt={r.model_name} className="aspect-video w-full object-cover transition-transform group-hover:scale-[1.02]" />
            </button>
            <div className="p-3.5">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm text-zinc-200">{r.model_name}</span>
                <span className="shrink-0 text-[11px] text-zinc-600">{fmtDate(r.created_at)}</span>
              </div>
              <div className="mt-1.5 flex items-center gap-2 text-[11px] text-zinc-500">
                <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">{r.quality}</span>
                <span>{r.camera}</span>
                <span>{r.width}×{r.height}</span>
                <span>{r.duration_s.toFixed(1)}s</span>
                <button onClick={() => remove(r)} className="ml-auto rounded p-1 text-zinc-600 opacity-0 transition-opacity hover:text-red-400 group-hover:opacity-100" title="Delete">
                  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3" /></svg>
                </button>
              </div>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {r.finishes.map((f) => (
                  <span key={f.finish_id} className="flex items-center gap-1 rounded-full border border-zinc-800 bg-zinc-950 py-0.5 pl-0.5 pr-2 text-[10px] text-zinc-400">
                    <img src={f.thumb} alt="" className="h-4 w-4 rounded-full object-cover" />
                    {f.name}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
      {(data || []).length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-800 py-24 text-center text-sm text-zinc-500">
          No renders yet — map finishes on a model and queue a render.
        </div>
      )}

      <Modal open={!!view} onClose={() => setView(null)} title={view?.model_name ?? ""} wide>
        {view && (
          <div>
            <img src={view.image_url} alt="" className="w-full rounded-lg border border-zinc-800" />
            <div className="mt-3 flex items-center justify-between text-xs text-zinc-500">
              <span>{view.quality} · {view.camera} · {view.width}×{view.height} · {view.duration_s.toFixed(1)}s · {fmtDate(view.created_at)}</span>
              <a href={view.image_url} download={`${view.model_name}-${view.id}.png`}
                className="rounded-lg border border-zinc-700 px-3 py-1.5 text-zinc-300 hover:bg-zinc-800">Download PNG</a>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
