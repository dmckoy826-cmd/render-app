import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api";
import type { SystemInfo } from "../types";

const NAV = [
  { to: "/models", label: "Models", d: "M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3 6.7 3.7L12 11.7 5.3 8 12 4.3ZM5 9.7l6 3.3v6.7l-6-3.3V9.7Zm14 0v6.7l-6 3.3v-6.7l6-3.3Z" },
  { to: "/finishes", label: "Finish library", d: "M4 4h7v7H4V4Zm9 0h7v7h-7V4ZM4 13h7v7H4v-7Zm9 0h7v7h-7v-7Z" },
  { to: "/presets", label: "Presets", d: "M6 2h12v20l-6-4-6 4V2Z" },
  { to: "/jobs", label: "Job queue", d: "M4 5h16v3H4V5Zm0 5.5h16v3H4v-3ZM4 16h16v3H4v-3Z" },
  { to: "/gallery", label: "Renders", d: "M4 5h16v14H4V5Zm2 2v7.2l4-3.2 3.5 2.8L18 10v7H6V7Z" },
];

interface ToastItem { id: number; msg: string; kind: "ok" | "err" }

function Toasts() {
  const [items, setItems] = useState<ToastItem[]>([]);
  useEffect(() => {
    const h = (e: Event) => {
      const { msg, kind } = (e as CustomEvent).detail as { msg: string; kind: "ok" | "err" };
      const id = Date.now() + Math.random();
      setItems((xs) => [...xs, { id, msg, kind }]);
      setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 4000);
    };
    window.addEventListener("app-toast", h);
    return () => window.removeEventListener("app-toast", h);
  }, []);
  return (
    <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2">
      {items.map((t) => (
        <div key={t.id} className={`toast-in rounded-lg border px-4 py-2.5 text-sm shadow-xl ${t.kind === "ok" ? "border-emerald-600/40 bg-emerald-950/90 text-emerald-200" : "border-red-600/40 bg-red-950/90 text-red-200"}`}>
          {t.msg}
        </div>
      ))}
    </div>
  );
}

export default function Layout() {
  const [sys, setSys] = useState<SystemInfo | null>(null);
  useEffect(() => {
    const load = () => api.get("/api/system/info").then(setSys).catch(() => undefined);
    load();
    const t = setInterval(load, 5000); // live worker heartbeat
    return () => clearInterval(t);
  }, []);
  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950">
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-amber-700 text-zinc-950">
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor"><path d="M12 2 3 7v10l9 5 9-5V7l-9-5Zm0 2.3 6.7 3.7L12 11.7 5.3 8 12 4.3ZM5 9.7l6 3.3v6.7l-6-3.3V9.7Zm14 0v6.7l-6 3.3v-6.7l6-3.3Z" /></svg>
          </div>
          <div>
            <div className="text-[15px] font-semibold tracking-tight text-zinc-100">FinishFlow</div>
            <div className="text-[11px] text-zinc-500">Rhino 8 · V-Ray automation</div>
          </div>
        </div>
        <nav className="mt-2 flex flex-col gap-1 px-3">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${isActive ? "bg-zinc-800/80 text-amber-300" : "text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200"}`}>
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="currentColor"><path d={n.d} /></svg>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-5 py-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
            <div className="text-[11px] uppercase tracking-wide text-zinc-500">Render engine</div>
            <div className="mt-1 flex items-start gap-2 text-xs text-zinc-300">
              <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${sys?.agent_connected ? "animate-pulse bg-emerald-400" : "bg-amber-400"}`} />
              <span>
                {sys ? (sys.agent_connected ? "Rhino worker connected" : sys.mode === "agent" ? "Waiting for Rhino worker…" : "Simulated engine") : "…"}
                {sys?.agent_connected && sys.agent_name && (
                  <span className="block text-[11px] text-emerald-400/80">
                    {sys.agent_name}
                    {sys.agent_last_seen_s != null && ` · seen ${Math.round(sys.agent_last_seen_s)}s ago`}
                  </span>
                )}
              </span>
            </div>
            <div className="mt-1 text-[11px] text-zinc-500">{sys?.target}</div>
          </div>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
      <Toasts />
    </div>
  );
}
