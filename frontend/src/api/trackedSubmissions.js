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

// Tracks which submissions the citizen has already given extraction feedback
// on, so the "did we understand this correctly?" prompt (normally only ever
// shown once, inside the just-submitted chat modal) can also surface later in
// the tracker list without re-asking forever once answered.
const FEEDBACK_GIVEN_KEY = 'civic_feedback_given_ids';

function getFeedbackGivenIds() {
  try {
    const raw = localStorage.getItem(FEEDBACK_GIVEN_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

export function hasFeedback(id) {
  return getFeedbackGivenIds().has(id);
}

export function markFeedbackGiven(id) {
  const ids = getFeedbackGivenIds();
  ids.add(id);
  localStorage.setItem(FEEDBACK_GIVEN_KEY, JSON.stringify([...ids]));
}
