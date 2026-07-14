/**
 * Lightweight shared invalidation mechanism — no React Query needed.
 *
 * How it works:
 *   - A module-level `token` integer acts as a "cache version."
 *   - Components call `useRefreshToken()` to get the current token value.
 *   - They include it in their useEffect dependency array, so whenever
 *     `invalidateComplaints()` is called anywhere (e.g., after a submission),
 *     the token bumps → all subscribed components re-run their fetch.
 *   - The subscriber set uses React state callbacks to trigger re-renders
 *     without needing a full Context provider tree.
 */
import { useState, useEffect } from 'react';

let token = 0;
const subscribers = new Set();

/** Call this after any mutation (new submission, status change, etc.) */
export function invalidateComplaints() {
  token += 1;
  subscribers.forEach(cb => cb(token));
}

/**
 * Returns the current refresh token. Include it in your useEffect deps.
 * The effect will re-run automatically whenever invalidateComplaints() is called.
 *
 * Usage:
 *   const refreshToken = useRefreshToken();
 *   useEffect(() => { load(); }, [refreshToken]);
 */
export function useRefreshToken() {
  const [t, setT] = useState(token);

  useEffect(() => {
    subscribers.add(setT);
    return () => subscribers.delete(setT);
  }, []);

  return t;
}
