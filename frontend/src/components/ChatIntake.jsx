import React, { useState, useRef, useEffect } from 'react';
import { Send, X, CheckCircle2, AlertTriangle, Bot, User } from 'lucide-react';
import { sendChatMessageStream, fetchLeaders } from '../api/client';
import { invalidateComplaints } from '../api/invalidation';
import { getRejectionMessage } from '../api/rejectionMessages';
import { addTrackedSubmission } from '../api/trackedSubmissions';
import ExtractionFeedbackCard from './ExtractionFeedbackCard';

const GREETING = 'Describe your complaint/Suggestion.';

export default function ChatIntake({ onClose, user }) {
  // `user` is the real logged-in citizen (from /auth/me), not a demo stand-in.

  // Each entry: { speaker: 'bot'|'citizen', displayText, englishText, questionKey }
  // The greeting is UI-only chrome, not part of the substantive conversation,
  // so it's excluded when building the `history` sent to the backend.
  const [messages, setMessages] = useState([
    { speaker: 'bot', displayText: GREETING, englishText: GREETING, isGreeting: true },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [submissionTypeHint, setSubmissionTypeHint] = useState(null);
  const [outcome, setOutcome] = useState(null); // null | { kind: 'submitted', complaintId, submissionType, confirmationText } | { kind: 'rejected', reason }
  // FR15 — text accumulated so far from the streaming reply (English-only;
  // stays empty for non-English turns, which arrive as one "final" event
  // with no preceding chunks — see stream_turn_reply's docstring).
  const [streamingText, setStreamingText] = useState('');
  const scrollRef = useRef(null);

  // FR9 — concerned-person selector. City/pincode narrow a leader dropdown;
  // editable throughout the conversation, sent (possibly changed) with every
  // turn — whichever value is set on the turn that actually creates the
  // Complaint row is what sticks. Optional: a citizen can submit without
  // picking a leader (routing to nobody in particular isn't a hard error at
  // this stage — Phase 5 owns dashboard-side jurisdiction scoping).
  const [city, setCity] = useState('');
  const [pincode, setPincode] = useState('');
  const [leaders, setLeaders] = useState([]);
  const [concernedLeaderId, setConcernedLeaderId] = useState('');

  useEffect(() => {
    if (!city.trim() && !pincode.trim()) { setLeaders([]); return; }
    const handle = setTimeout(() => {
      fetchLeaders({ city: city.trim(), pincode: pincode.trim() })
        .then(setLeaders)
        .catch(() => setLeaders([]));
    }, 400); // debounce while typing
    return () => clearTimeout(handle);
  }, [city, pincode]);
  // Captures the citizen's FIRST substantive message (the actual issue description),
  // so the tracker preview never ends up showing a later short follow-up reply
  // (e.g. a bare pincode) instead of the real complaint text.
  const firstMessageRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, sending]);

  const handleSend = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending || outcome) return;

    if (firstMessageRef.current === null) firstMessageRef.current = text;

    setInput('');
    setSending(true);
    setStreamingText('');

    const citizenTurnIndex = messages.length;
    setMessages((prev) => [...prev, { speaker: 'citizen', displayText: text, englishText: text }]);

    try {
      const history = messages
        .filter((m) => !m.isGreeting)
        .map((m) => ({ speaker: m.speaker, english_text: m.englishText, question_key: m.questionKey || null }));

      const res = await sendChatMessageStream({
        new_message: text,
        history,
        submission_type_hint: submissionTypeHint,
        citizen_first_name: user.first_name,
        citizen_last_name: user.last_name,
        citizen_phone: user.phone,
        concerned_leader_id: concernedLeaderId || null,
      }, (chunk) => setStreamingText((prev) => prev + chunk));

      // Backfill the just-sent citizen turn with its English-normalized text
      setMessages((prev) => {
        const updated = [...prev];
        updated[citizenTurnIndex] = { ...updated[citizenTurnIndex], englishText: res.new_message_english };
        return updated;
      });

      if (res.kind === 'question') {
        setSubmissionTypeHint(res.submission_type_hint || null);
        setMessages((prev) => [
          ...prev,
          {
            speaker: 'bot',
            displayText: res.question_text,
            englishText: res.question_text_english,
            questionKey: res.question_key,
          },
        ]);
      } else if (res.kind === 'rejected') {
        setOutcome({ kind: 'rejected', reason: res.rejection_reason });
      } else if (res.kind === 'rate_limited') {
        setOutcome({ kind: 'rate_limited', message: res.rate_limit_message });
      } else if (res.kind === 'submitted') {
        setMessages((prev) => [...prev, { speaker: 'bot', displayText: res.confirmation_text, englishText: res.confirmation_text }]);
        addTrackedSubmission(user.id, {
          id: res.complaint_id,
          type: res.submission_type,
          preview: (firstMessageRef.current || text).slice(0, 140),
          created_at: new Date().toISOString(),
        });
        invalidateComplaints();
        setOutcome({
          kind: 'submitted',
          complaintId: res.complaint_id,
          submissionType: res.submission_type,
          confirmationText: res.confirmation_text,
        });
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { speaker: 'bot', displayText: 'Something went wrong sending that — please try again.', englishText: '' },
      ]);
    } finally {
      setSending(false);
      setStreamingText('');
    }
  };

  const rejection = outcome?.kind === 'rejected' ? getRejectionMessage(outcome.reason) : null;

  // FR9 — the concerned person is what routes a submission to a leader's
  // dashboard (every leader-facing query filters on concerned_leader_id).
  // It used to be labelled "optional" and nothing enforced it, so the default
  // path — start typing without touching the city/pincode fields — produced
  // complaints with no leader assigned, which no dashboard would ever show:
  // the citizen got a "Submitted Successfully" confirmation for a submission
  // that had, in practice, gone nowhere. It's required before the first
  // message now, and stays editable for the rest of the conversation.
  const needsLeader = !concernedLeaderId;

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white w-full max-w-xl rounded-lg shadow-2xl border border-gray-200 relative overflow-hidden max-h-[90vh] flex flex-col">
        {/* Modal header */}
        <div className="bg-[#0e75c6] text-white px-4 py-2.5 flex items-center justify-between rounded-t-lg shrink-0">
          <span className="text-sm font-bold">File a Complaint / Suggestion</span>
          <button onClick={onClose}><X className="w-4 h-4" /></button>
        </div>

        {/* FR9 — concerned-person selector, above the conversation thread and
            editable throughout. Hidden once the conversation has ended (an
            outcome exists) — nothing left to route at that point. */}
        {!outcome && (
          <div className="px-4 py-2.5 border-b border-gray-200 bg-gray-50 flex flex-wrap items-center gap-2 shrink-0">
            <input
              type="text" value={city} onChange={(e) => setCity(e.target.value)}
              placeholder="City"
              className="w-24 border border-gray-300 rounded-full px-3 py-1 text-xs text-black focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
            <input
              type="text" value={pincode} onChange={(e) => setPincode(e.target.value)}
              placeholder="Pincode"
              className="w-24 border border-gray-300 rounded-full px-3 py-1 text-xs text-black focus:outline-none focus:ring-1 focus:ring-blue-400"
            />
            <select
              value={concernedLeaderId} onChange={(e) => setConcernedLeaderId(e.target.value)}
              className={`flex-1 min-w-[140px] border rounded-full px-3 py-1 text-xs text-black bg-white focus:outline-none focus:ring-1 focus:ring-blue-400 ${
                needsLeader ? 'border-amber-400' : 'border-gray-300'
              }`}
            >
              <option value="">Concerned person (required)</option>
              {leaders.map((l) => (
                <option key={l.id} value={l.id}>{l.name} — {l.city}, {l.pincode}</option>
              ))}
            </select>
            {needsLeader && (
              <p className="w-full text-[10px] text-amber-700">
                {leaders.length === 0
                  ? 'Enter your city (and pincode, if you know it) to find the person responsible for your area.'
                  : 'Choose the concerned person so your submission reaches the right leader.'}
              </p>
            )}
          </div>
        )}

        {outcome?.kind === 'submitted' ? (
          <div className="px-5 py-6 overflow-y-auto">
            <div className="text-center">
              <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto mb-3" />
              <p className="font-bold text-black text-sm mb-1">Submitted Successfully</p>
              <p className="text-xs text-gray-600 mb-3">
                Your {outcome.submissionType} is being reviewed. Check{' '}
                <strong>{outcome.submissionType === 'complaint' ? 'Track your Complaint' : 'Track your Suggestion'}</strong> for its status.
              </p>
              <div className="bg-gray-50 border border-gray-200 rounded p-2 mb-2">
                <p className="text-[10px] text-gray-500 uppercase font-semibold mb-0.5">Reference ID</p>
                <p className="font-mono text-xs text-black break-all">{outcome.complaintId}</p>
              </div>
            </div>

            <ExtractionFeedbackCard
              complaintId={outcome.complaintId}
              submissionType={outcome.submissionType}
            />

            <div className="text-center mt-4">
              <button onClick={onClose} className="bg-[#0e75c6] text-white px-4 py-1.5 rounded text-xs font-semibold hover:bg-[#054483]">Done</button>
            </div>
          </div>
        ) : (
          <>
            <div ref={scrollRef} className="px-4 py-4 flex-1 overflow-y-auto space-y-3 bg-[#f5f9fd]" style={{ minHeight: '360px' }}>
              {messages.map((m, i) => (
                <div key={i} className={`flex items-start gap-2 ${m.speaker === 'citizen' ? 'flex-row-reverse' : ''}`}>
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center shrink-0 ${m.speaker === 'citizen' ? 'bg-[#0e75c6]' : 'bg-gray-300'}`}>
                    {m.speaker === 'citizen' ? <User className="w-3.5 h-3.5 text-white" /> : <Bot className="w-3.5 h-3.5 text-gray-700" />}
                  </div>
                  <div
                    className={`max-w-[75%] rounded-lg px-3 py-2 text-xs leading-relaxed ${
                      m.speaker === 'citizen' ? 'bg-[#0e75c6] text-white' : 'bg-white border border-gray-200 text-black'
                    }`}
                  >
                    {m.displayText}
                  </div>
                </div>
              ))}

              {sending && (
                <div className="flex items-start gap-2">
                  <div className="w-6 h-6 rounded-full flex items-center justify-center shrink-0 bg-gray-300">
                    <Bot className="w-3.5 h-3.5 text-gray-700" />
                  </div>
                  {/* FR15 — shows the reply growing token-by-token as it streams in;
                      falls back to a plain "Typing…" indicator before the first
                      chunk arrives, or for non-English turns (delivered as one
                      complete block, not streamed — see ChatIntake's streamingText note). */}
                  <div className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-xs text-black">
                    {streamingText || <span className="text-gray-400">Typing…</span>}
                  </div>
                </div>
              )}

              {outcome?.kind === 'rejected' && rejection && (
                <div className={`flex items-start gap-2 p-2.5 rounded border ${rejection.tone === 'emergency' ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'}`}>
                  <AlertTriangle className={`w-4 h-4 shrink-0 mt-0.5 ${rejection.tone === 'emergency' ? 'text-red-500' : 'text-amber-500'}`} />
                  <div>
                    <p className="text-xs font-bold text-gray-800 mb-0.5">{rejection.title}</p>
                    <p className="text-xs text-gray-700">{rejection.body}</p>
                  </div>
                </div>
              )}

              {outcome?.kind === 'rate_limited' && (
                <div className="flex items-start gap-2 p-2.5 rounded border bg-amber-50 border-amber-200">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-500" />
                  <div>
                    <p className="text-xs font-bold text-gray-800 mb-0.5">Submission limit reached</p>
                    <p className="text-xs text-gray-700">{outcome.message}</p>
                  </div>
                </div>
              )}
            </div>

            <form onSubmit={handleSend} className="border-t border-gray-200 px-3 py-2.5 flex items-center gap-2 shrink-0 bg-white">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={sending || !!outcome || needsLeader}
                placeholder={
                  outcome ? 'This conversation has ended.'
                    : needsLeader ? 'Select a concerned person above to start…'
                    : 'Type your message...'
                }
                className="flex-1 px-3 py-2 text-xs text-black border border-gray-300 rounded-full bg-[#eaf4ff] focus:outline-none focus:ring-1 focus:ring-blue-400 disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={sending || !!outcome || needsLeader || !input.trim()}
                className="w-9 h-9 rounded-full bg-[#0e75c6] text-white flex items-center justify-center shrink-0 hover:bg-[#054483] disabled:opacity-40 transition-colors"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
