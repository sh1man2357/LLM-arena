import { useCallback, useEffect, useState } from 'react';

export class ReadError extends Error {
  constructor(message: string, readonly status?: number) { super(message); }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...options, headers: { ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try { const detail = await response.json(); message = detail.message || message; } catch { /* network / proxy response */ }
    throw new ReadError(message, response.status);
  }
  return response.json();
}

export function useResource<T>(path: string | null, revision = 0) {
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt(value => value + 1), []);
  const [state, setState] = useState<{path: string | null; data?: T; error: string; errorStatus?: number; pending: boolean}>({path: null, error: '', pending: false});
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    // Keep the last confirmed value only for this exact resource/filter.
    setState(previous => ({path, data: previous.path === path ? previous.data : undefined, error: '', pending: true}));
    api<T>(path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({path, data, error: '', pending: false});
    }).catch(err => {
      if (!controller.signal.aborted) setState(previous => ({...previous, path,
        data: err.status === 403 || err.status === 404 ? undefined : previous.data,
        error: err.message, errorStatus: err.status, pending: false}));
    });
    return () => controller.abort();
  }, [path, revision, attempt]);
  const current = path !== null && state.path === path;
  const data = current ? state.data : undefined;
  const pending = path !== null && (!current || state.pending);
  return {data, error: current ? state.error : '', errorStatus: current ? state.errorStatus : undefined,
    loading: pending && data === undefined, refreshing: pending && data !== undefined, retry};
}
