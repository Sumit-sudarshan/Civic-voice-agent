const STORAGE_PREFIX = 'civic_tracked_submissions_';

function storageKey(user) {
  return `${STORAGE_PREFIX}${user}`;
}

export function getTrackedSubmissions(user) {
  try {
    const raw = localStorage.getItem(storageKey(user));
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function addTrackedSubmission(user, submission) {
  const existing = getTrackedSubmissions(user);
  const updated = [submission, ...existing];
  localStorage.setItem(storageKey(user), JSON.stringify(updated));
}

export function removeTrackedSubmissions(user, ids) {
  const idSet = new Set(ids);
  const remaining = getTrackedSubmissions(user).filter(t => !idSet.has(t.id));
  localStorage.setItem(storageKey(user), JSON.stringify(remaining));
  return remaining;
}
