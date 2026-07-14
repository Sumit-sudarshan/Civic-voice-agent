import React, { useState, useEffect, useRef } from 'react';
import { Loader2, CheckCircle2, ThumbsUp, ThumbsDown, Sparkles } from 'lucide-react';
import { fetchSubmissionStatus, sendExtractionFeedback } from '../api/client';

// Eval Layer 2 (citizen-side): once the pipeline finishes analysing a fresh
// submission, show the citizen what the agent understood and ask if it's right.
// Their answer is logged as ground-truth feedback on extraction quality. This is
// a lightweight simulation of a feedback loop — capture only, no correction is
// pushed back into the live record.

function Field({ label, value }) {
  const empty = !value || String(value).toLowerCase() === 'not specified';
  return (
    <div className="flex items-start gap-2">
      <span className="text-[10px] uppercase font-semibold text-gray-500 w-24 flex-shrink-0 mt-0.5">{label}</span>
      <span className={empty ? 'text-gray-400 italic text-[11px]' : 'text-gray-900 text-[12px]'}>
        {empty ? 'Not identified' : value}
      </span>
    </div>
  );
}

export default function ExtractionFeedbackCard({ complaintId, submissionType }) {
  const [record, setRecord] = useState(null);
  const [status, setStatus] = useState('analyzing'); // analyzing | ready | failed
  const [choice, setChoice] = useState(null);         // null | 'up' | 'down'
  const [correction, setCorrection] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const timerRef = useRef(null);

  // Poll the submission until the background pipeline marks it done.
  useEffect(() => {
    let cancelled = false;
    let attempts = 0;

    const poll = async () => {
      attempts += 1;
      try {
        const data = await fetchSubmissionStatus(submissionType, complaintId);
        if (cancelled) return;
        if (data.pipeline_status === 'done') {
          setRecord(data);
          setStatus('ready');
          return;
        }
        if (data.pipeline_status === 'failed') {
          setStatus('failed');
          return;
        }
      } catch {
        // 404 right after submit is possible; keep polling a bit.
      }
      if (attempts > 40) { // ~80s ceiling, then stop spinning
        if (!cancelled) setStatus('failed');
        return;
      }
      timerRef.current = setTimeout(poll, 2000);
    };

    poll();
    return () => { cancelled = true; clearTimeout(timerRef.current); };
  }, [complaintId, submissionType]);

  const submit = async (isCorrect) => {
    setSubmitting(true);
    try {
      await sendExtractionFeedback(complaintId, {
        is_correct: isCorrect,
        correction: isCorrect ? null : (correction.trim() || null),
      });
      setDone(true);
    } catch {
      setDone(true); // don't trap the citizen on a failed feedback POST
    } finally {
      setSubmitting(false);
    }
  };

  if (status === 'analyzing') {
    return (
      <div className="mt-3 bg-white border border-gray-200 rounded-lg p-4 flex items-center gap-3">
        <Loader2 className="w-4 h-4 text-[#0e75c6] animate-spin" />
        <div>
          <p className="text-xs font-semibold text-gray-800">Analyzing your submission…</p>
          <p className="text-[11px] text-gray-500">We'll show you what we understood in a moment.</p>
        </div>
      </div>
    );
  }

  if (status === 'failed') {
    return null; // silently skip the feedback step if analysis didn't complete in time
  }

  if (done) {
    return (
      <div className="mt-3 bg-green-50 border border-green-200 rounded-lg p-3 flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0" />
        <p className="text-xs text-green-800">Thanks! Your feedback helps us improve accuracy.</p>
      </div>
    );
  }

  return (
    <div className="mt-3 bg-white border border-gray-200 rounded-lg p-4">
      <div className="flex items-center gap-1.5 mb-2.5">
        <Sparkles className="w-3.5 h-3.5 text-amber-500" />
        <span className="text-[10px] font-bold uppercase tracking-wider text-gray-600">Here's what we understood</span>
      </div>

      <div className="space-y-1.5 mb-3">
        <Field label="Category" value={record?.category} />
        {submissionType === 'complaint' && <Field label="Urgency" value={record?.urgency_level} />}
        <Field label="Issue" value={record?.extracted_issue_summary} />
        <Field label="Location" value={record?.extracted_location} />
        <Field label="Who's affected" value={record?.extracted_affected_parties} />
        <Field label="Ask" value={record?.extracted_ask} />
      </div>

      {choice !== 'down' ? (
        <div className="border-t border-gray-100 pt-3">
          <p className="text-xs font-medium text-gray-700 mb-2">Did we understand this correctly?</p>
          <div className="flex gap-2">
            <button
              onClick={() => submit(true)}
              disabled={submitting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-green-200 text-green-700 bg-green-50 hover:bg-green-100 text-xs font-semibold disabled:opacity-50 transition-colors"
            >
              <ThumbsUp className="w-3.5 h-3.5" /> Yes, correct
            </button>
            <button
              onClick={() => setChoice('down')}
              disabled={submitting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-gray-200 text-gray-700 bg-white hover:bg-gray-50 text-xs font-semibold disabled:opacity-50 transition-colors"
            >
              <ThumbsDown className="w-3.5 h-3.5" /> Not quite
            </button>
          </div>
        </div>
      ) : (
        <div className="border-t border-gray-100 pt-3">
          <p className="text-xs font-medium text-gray-700 mb-2">What did we get wrong? (optional)</p>
          <textarea
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            rows={2}
            placeholder="e.g. the location is actually Sector 7, not Sector 4"
            className="w-full text-xs border border-gray-200 rounded-lg p-2 focus:outline-none focus:ring-2 focus:ring-black/5 resize-none"
          />
          <div className="flex gap-2 mt-2">
            <button
              onClick={() => submit(false)}
              disabled={submitting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#0e75c6] text-white hover:bg-[#054483] text-xs font-semibold disabled:opacity-50 transition-colors"
            >
              {submitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Submit feedback
            </button>
            <button
              onClick={() => setChoice(null)}
              disabled={submitting}
              className="px-3 py-1.5 rounded-lg text-gray-500 hover:text-black text-xs font-semibold transition-colors"
            >
              Back
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
