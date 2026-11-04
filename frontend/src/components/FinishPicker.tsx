import { useState } from "react";
import Modal from "./Modal";
import { api } from "../api";
import { usePoll } from "../hooks";
import { CATEGORY_COLOR, CATEGORY_LABEL, type Category, type Finish } from "../types";

const CATS: ("all" | Category)[] = ["all", "laminate", "pet", "product_finish", "other"];

export default function FinishPicker({ open, onClose, onPick, title = "Assign finish" }: {
  open: boolean; onClose: () => void; onPick: (f: Finish) => void; title?: string;
}) {
  const { data } = usePoll<Finish[]>(() => api.get("/api/finishes"), 60000, open);
  const [cat, setCat] = useState<"all" | Category>("all");
  const [q, setQ] = useState("");
  const list = (data || []).filter((f) =>
    (cat === "all" || f.category === cat) &&
    (!q || `${f.name} ${f.tags}`.toLowerCase().includes(q.toLowerCase())));
  return (
    <Modal open={open} onClose={onClose} title={title} wide>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {CATS.map((c) => (
          <button key={c} onClick={() => setCat(c)}
            className={`rounded-full border px-3 py-1 text-xs ${cat === c ? "border-amber-500/50 bg-amber-500/15 text-amber-300" : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"}`}>
            {c === "all" ? "All" : CATEGORY_LABEL[c]}
          </button>
        ))}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search finishes…"
          className="ml-auto w-52 rounded-lg border border-zinc-700 bg-zinc-950 px-3 py-1.5 text-sm text-zinc-200 placeholder-zinc-500 outline-none focus:border-amber-500/60" />
      </div>
      {list.length === 0 && <p className="py-10 text-center text-sm text-zinc-500">No finishes match.</p>}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {list.map((f) => (
          <button key={f.id} onClick={() => { onPick(f); onClose(); }}
            className="group overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 text-left transition-colors hover:border-amber-500/60">
            <div className="aspect-square w-full overflow-hidden">
              <img src={f.thumb_url} alt={f.name} className="h-full w-full object-cover transition-transform group-hover:scale-105" />
            </div>
            <div className="p-2.5">
              <div className="truncate text-sm text-zinc-200">{f.name}</div>
              <div className="mt-1 flex items-center justify-between gap-1">
                <span className={`rounded border px-1.5 py-0.5 text-[10px] ${CATEGORY_COLOR[f.category]}`}>{CATEGORY_LABEL[f.category]}</span>
                <span className="text-[10px] text-zinc-500">{f.swatch_width_in}×{f.swatch_height_in}&quot;</span>
              </div>
            </div>
          </button>
        ))}
      </div>
    </Modal>
  );
}
