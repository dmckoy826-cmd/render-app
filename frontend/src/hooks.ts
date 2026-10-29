import { useCallback, useEffect, useRef, useState } from "react";

export function usePoll<T>(fn: () => Promise<T>, intervalMs: number, active = true) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const load = useCallback(async () => {
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
    if (!active) return;
    const t = setInterval(load, intervalMs);
    return () => clearInterval(t);
  }, [active, intervalMs, load]);

  return { data, error, refresh: load, setData };
}
