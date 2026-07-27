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
    case 'location':
      return 'Is the area shown here correct?';
    default:
      return 'Did the AI get this right?';
  }
}

// Which Complaint field(s) a "No" answer on each aspect can correct — must
// match backend/app/api/complaints.py's _CORRECTABLE_FIELDS allowlist.
// 'location' was missing entirely before (area is a common, real extraction
// error), so a leader had no way to flag or fix a wrong area at all.
export const ASPECT_FIELDS = {
  labelling: [
    { key: 'category', label: 'Correct category' },
    { key: 'urgency_level', label: 'Correct urgency', complaintOnly: true },
  ],
  summary: [{ key: 'extracted_issue_summary', label: 'Correct summary' }],
  affected_and_ask: [
    { key: 'extracted_affected_parties', label: "Correct who's affected" },
    { key: 'extracted_ask', label: "Correct what's being asked" },
  ],
  location: [{ key: 'location_area', label: 'Correct area' }],
};

const ASPECTS = ['labelling', 'summary', 'affected_and_ask', 'location'];

// Returns a random aspect to ask about — always, so the prompt shows up
// reliably every time an eligible issue is expanded (see hasAnsweredLeaderFeedback
// for the "don't ask again once answered" half of the gating).
export function pickLeaderFeedbackAspect() {
  return ASPECTS[Math.floor(Math.random() * ASPECTS.length)];
}
