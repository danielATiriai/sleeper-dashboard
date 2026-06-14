import { useEffect, useState } from "react";

interface State<T> { data: T | null; error: Error | null; loading: boolean }

// Tiny data-loading hook for the static bundles. `deps` re-runs the loader.
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true });
  useEffect(() => {
    let alive = true;
    setState({ data: null, error: null, loading: true });
    fn()
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState({ data: null, error, loading: false }));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}
