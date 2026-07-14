export const REJECTION_MESSAGES = {
  abusive_or_harmful: {
    title: 'Submission Not Registered',
    body: 'Your message contained abusive or harmful language and no describable civic issue, so it was not registered. Please resubmit describing the actual issue in respectful language.',
    tone: 'warning',
  },
  personal_emergency: {
    title: 'This Is Not a Civic Complaint',
    body: 'This looks like a personal emergency, not a civic infrastructure issue — this portal cannot dispatch emergency help. Please call 112 (or 108 for ambulance) immediately.',
    tone: 'emergency',
  },
  spam_or_gibberish: {
    title: 'Submission Not Registered',
    body: "We couldn't identify a valid complaint or suggestion in your message. Please resubmit with a clear description of the issue.",
    tone: 'info',
  },
  off_topic: {
    title: 'Submission Not Registered',
    body: 'This message does not appear to relate to a civic/local government issue, so it was not registered.',
    tone: 'info',
  },
  too_vague_to_process: {
    title: 'More Detail Needed',
    body: 'We could tell this relates to a civic issue, but there was not enough detail to act on it. Please resubmit with specifics (what, where).',
    tone: 'info',
  },
  area_missing: {
    title: "Can't Proceed With This Request",
    body: "We asked a few times but couldn't get a clear area for this issue, so we can't proceed. Please start a new complaint and share the area (e.g. the locality or neighbourhood name) up front.",
    tone: 'warning',
  },
  pincode_missing: {
    title: "Can't Proceed With This Request",
    body: "We asked a few times but couldn't get a usable PIN code for this issue, so we can't proceed. Please start a new complaint and share the PIN code up front, or say clearly if you don't know it.",
    tone: 'warning',
  },
};

export function getRejectionMessage(reviewReason) {
  return REJECTION_MESSAGES[reviewReason] || null;
}
