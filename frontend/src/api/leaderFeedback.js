// Decides WHICH single facet to ask the leader about when they expand an
// issue. Originally gated behind a cooldown + random show-probability so it
// would never nag across a real review session — relaxed to always ask (once
// per issue, like the citizen-side ExtractionFeedbackCard) since for a live
// demo the reviewer needs to reliably see it every time, not on a coin flip.

const ANSWERED_KEY = 'civic_leader_feedback_answered_ids';

function getAnsweredIds() {
  try {
    const raw = localStorage.getItem(ANSWERED_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

// Once the leader has answered (or explicitly dismissed) for a given
// complaint, don't ask again for it — mirrors how the citizen-side feedback
// card disappears for good once answered.
export function hasAnsweredLeaderFeedback(complaintId) {
  return getAnsweredIds().has(complaintId);
}

export function markLeaderFeedbackAnswered(complaintId) {
  const ids = getAnsweredIds();
  ids.add(complaintId);
  localStorage.setItem(ANSWERED_KEY, JSON.stringify([...ids]));
}

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

// Returns a random aspect to ask about — always, so the prompt shows up
// reliably every time an eligible issue is expanded (see hasAnsweredLeaderFeedback
// for the "don't ask again once answered" half of the gating).
export function pickLeaderFeedbackAspect() {
  return ASPECTS[Math.floor(Math.random() * ASPECTS.length)];
}
