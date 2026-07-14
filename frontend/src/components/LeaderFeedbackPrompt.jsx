import React, { useState } from 'react';
import { ThumbsUp, ThumbsDown, Sparkles, Check, X } from 'lucide-react';
import { sendExtractionFeedback } from '../api/client';
import { pickLeaderFeedbackAspect, buildQuestion, hasAnsweredLeaderFeedback, markLeaderFeedbackAnswered } from '../api/leaderFeedback';

// A spot-check shown to the leader inside an expanded issue, asking ONE
// rotating question (labelling / summary / affected+ask). Shows reliably every
// time an eligible issue is expanded, and disappears for good once the leader
// answers or dismisses it for that complaint — same persisted-once-answered
// pattern as the citizen-side ExtractionFeedbackCard.
export default function LeaderFeedbackPrompt({ issue }) {
  const eligible = issue?.pipeline_status === 'done'
    && issue?.is_valid_submission === true
    && !hasAnsweredLeaderFeedback(issue.id);

  // Decide once per mount whether (and what) to ask. Lazy init so it doesn't
  // re-roll on every render and only "spends" an eligibility slot when eligible.
  const [aspect] = useState(() => (eligible ? pickLeaderFeedbackAspect() : null));
  const [phase, setPhase] = useState('ask'); // 'ask' | 'note' | 'done' | 'dismissed'
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!aspect || phase === 'dismissed') return null;

  const submit = async (isCorrect) => {
    setSubmitting(true);
    try {
      await sendExtractionFeedback(issue.id, {
        is_correct: isCorrect,
        correction: isCorrect ? null : (note.trim() || null),
        source: 'leader',
        aspect,
      });
    } catch { /* don't trap the leader on a failed POST */ }
    finally {
      setSubmitting(false);
      setPhase('done');
      markLeaderFeedbackAnswered(issue.id);
    }
  };

  if (phase === 'done') {
    return (
      <div className="mt-3 flex items-center gap-1.5 text-[11px] text-indigo-700 bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2">
        <Check className="w-3.5 h-3.5" /> Thanks — noted for improving accuracy.
      </div>
    );
  }

  return (
    <div className="mt-3 bg-indigo-50/60 border border-indigo-100 rounded-lg px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-indigo-500 mt-0.5 shrink-0" />
          <p className="text-[11px] text-gray-700 leading-snug">
            <span className="font-semibold text-indigo-700">Help us improve: </span>
            {buildQuestion(aspect, issue)}
          </p>
        </div>
        <button
          onClick={() => { setPhase('dismissed'); markLeaderFeedbackAnswered(issue.id); }}
          className="text-gray-400 hover:text-gray-700 shrink-0"
          title="Dismiss"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {phase === 'ask' ? (
        <div className="flex gap-2 mt-2 pl-5">
          <button
            onClick={() => submit(true)}
            disabled={submitting}
            className="flex items-center gap-1 px-2.5 py-1 rounded border border-green-200 text-green-700 bg-green-50 hover:bg-green-100 text-[11px] font-semibold disabled:opacity-50 transition-colors"
          >
            <ThumbsUp className="w-3 h-3" /> Yes
          </button>
          <button
            onClick={() => setPhase('note')}
            disabled={submitting}
            className="flex items-center gap-1 px-2.5 py-1 rounded border border-gray-200 text-gray-700 bg-white hover:bg-gray-50 text-[11px] font-semibold disabled:opacity-50 transition-colors"
          >
            <ThumbsDown className="w-3 h-3" /> No
          </button>
        </div>
      ) : (
        <div className="mt-2 pl-5">
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="What should it have been? (optional)"
            className="w-full text-[11px] border border-gray-200 rounded px-2 py-1 focus:outline-none focus:ring-2 focus:ring-black/5"
          />
          <div className="flex gap-2 mt-1.5">
            <button
              onClick={() => submit(false)}
              disabled={submitting}
              className="px-2.5 py-1 rounded bg-indigo-600 text-white hover:bg-indigo-700 text-[11px] font-semibold disabled:opacity-50 transition-colors"
            >
              Submit
            </button>
            <button
              onClick={() => setPhase('ask')}
              disabled={submitting}
              className="px-2.5 py-1 rounded text-gray-500 hover:text-black text-[11px] font-semibold transition-colors"
            >
              Back
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
