import { useState, useEffect } from 'react';

/**
 * Returns a debounced copy of `value` that only updates after `delay` ms
 * of silence. Use in search inputs so a fetch isn't fired on every keystroke.
 *
 * Usage:
 *   const debouncedQuery = useDebounce(query, 300);
 *   useEffect(() => { if (debouncedQuery !== undefined) search(debouncedQuery); }, [debouncedQuery]);
 */
export function useDebounce(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
