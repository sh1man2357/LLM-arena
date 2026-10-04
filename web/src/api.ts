import { useEffect, useState } from 'react';

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...options, headers: { ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
  if (!response.ok) {
    let message = `请求失败 (${response.status})`;
    try { const detail = await response.json(); message = detail.message || message; } catch { /* network / proxy response */ }
    throw new Error(message);
  }
  return response.json();
}

export function useResource<T>(path: string | null, revision = 0) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setError('');
    api<T>(path, { signal: controller.signal }).then(value => { setData(value); setLoadedPath(path); setLoading(false); })
      .catch(err => { if (err.name !== 'AbortError') { setError(err.message); setLoadedPath(path); setLoading(false); } });
    return () => controller.abort();
  }, [path, revision]);
  return { data: loadedPath === path ? data : undefined, error: loadedPath === path ? error : '', loading: path !== null && (loadedPath !== path || loading) };
}
