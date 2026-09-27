"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Loadable<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => Promise<void>;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
};

/** Load data on mount / when deps change; ignores responses from stale requests. */
export function useApi<T>(loader: () => Promise<T>, deps: React.DependencyList): Loadable<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const reload = useCallback(async () => {
    const id = ++seq.current;
    setLoading(true);
    try {
      const result = await loaderRef.current();
      if (id === seq.current) {
        setData(result);
        setError(null);
      }
    } catch (err) {
      if (id === seq.current) setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- caller controls deps
  }, deps);

  return { data, error, loading, reload, setData };
}

/** Re-run ``fn`` every ``ms`` while ``active``. */
export function useInterval(fn: () => void, ms: number, active: boolean) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => ref.current(), ms);
    return () => clearInterval(id);
  }, [ms, active]);
}
