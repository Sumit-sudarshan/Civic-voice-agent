// Decides WHEN to quietly ask the leader for a spot-check on the AI's output,
// and WHICH single facet to ask about. Deliberately infrequent so it never
// nags: at most one prompt per cooldown window, and even then only sometimes.

const COOLDOWN_MS = 1 * 60 * 1000;  // never ask more than once per minute (demo-friendly cadence)
const SHOW_PROBABILITY = 0.6;       // ~3 in 5 eligible opens, so it shows up reliably during a review
const LS_KEY = 'civic_leader_feedback_at';

// Each aspect maps to one short, human question. `is_correct` = yes.
export function buildQuestion(aspect, issue) {
  const cat = issue.category || 'this category';
  const urg = issue.urgency_level ? `, ${issue.urgency_level} urgency` : '';
  switch (aspect) {
    case 'labelling':
      return `Quick check — is this correctly categorised as ${cat}${urg}?`;
    case 'summary':
      return 'Is the one-line summary an accurate reflection of the complaint?';
    case 'affected_and_ask':
      return "Is the 'who's affected' and 'what's being asked' genuinely useful here?";
    default:
      return 'Did the AI get this right?';
  }
}

const ASPECTS = ['labelling', 'summary', 'affected_and_ask'];

// Returns an aspect string to ask about, or null if we shouldn't ask right now.
// Records the timestamp as soon as we decide to ask, so the cooldown holds
// regardless of whether the leader answers or dismisses.
export function pickLeaderFeedbackAspect() {
  let last = 0;
  try { last = Number(localStorage.getItem(LS_KEY)) || 0; } catch { /* ignore */ }
  if (Date.now() - last < COOLDOWN_MS) return null;
  if (Math.random() > SHOW_PROBABILITY) return null;

  try { localStorage.setItem(LS_KEY, String(Date.now())); } catch { /* ignore */ }
  return ASPECTS[Math.floor(Math.random() * ASPECTS.length)];
}
