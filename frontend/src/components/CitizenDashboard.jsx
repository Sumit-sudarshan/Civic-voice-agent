import React, { useState, useEffect } from 'react';
import { Home, LogOut, FileText, AlertTriangle, Clock, RefreshCw, MessageSquareText, ChevronDown, ChevronUp } from 'lucide-react';
import { fetchSubmissionStatus, fetchMyComplaints } from '../api/client';
import { getRejectionMessage } from '../api/rejectionMessages';
import { getTrackedSubmissions, removeTrackedSubmissions, hasFeedback, markFeedbackGiven } from '../api/trackedSubmissions';
import ChatIntake from './ChatIntake';
import ExtractionFeedbackCard from './ExtractionFeedbackCard';

function SubmissionTracker({ user, type }) {
  const [tracked, setTracked]   = useState(() => getTrackedSubmissions(user).filter(t => t.type === type));
  const [statuses, setStatuses] = useState({}); // id -> live submission record
  const [loading, setLoading]   = useState(true);
  // Tracks which rows have already had extraction feedback given, so the
  // "did we understand this correctly?" card disappears for good once answered
  // (persisted via api/trackedSubmissions.js so it survives a page reload).
  const [givenIds, setGivenIds] = useState(() => new Set());
  const feedbackAnswered = (id) => givenIds.has(id) || hasFeedback(id);
  // Which rows are expanded to show "what our system understood" — collapsed
  // by default, same pattern as the leader dashboard's IssueRow.
  const [expandedIds, setExpandedIds] = useState(() => new Set());
  const toggleExpanded = (id) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const loadStatuses = async (list = tracked, { silent = false } = {}) => {
    if (!silent) setLoading(true);
    const results = await Promise.all(
      list.map(async (t) => {
        try {
          return [t.id, await fetchSubmissionStatus(t.type, t.id), false];
        } catch (err) {
          return [t.id, null, !!err.notFound];
        }
      })
    );

    const goneIds = results.filter(([, , gone]) => gone).map(([id]) => id);
    if (goneIds.length > 0) {
      const remaining = removeTrackedSubmissions(user, goneIds).filter(t => t.type === type);
      setTracked(remaining);
    }

    setStatuses(Object.fromEntries(results.filter(([, , gone]) => !gone).map(([id, status]) => [id, status])));
    if (!silent) setLoading(false);
  };

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const local = getTrackedSubmissions(user).filter(t => t.type === type);
      // FR6 — merge in the server's own record of this citizen's submissions
      // (scoped by their verified session, not this browser's localStorage),
      // so history survives a new device or a cleared browser. Best-effort:
      // a fetch failure just falls back to whatever localStorage already had.
      let merged = local;
      try {
        const mine = await fetchMyComplaints();
        const knownIds = new Set(local.map((t) => t.id));
        const fromServer = mine
          .filter((c) => c.submission_type === type && !knownIds.has(c.id))
          .map((c) => ({ id: c.id, type: c.submission_type, preview: c.raw_text?.slice(0, 140), created_at: c.created_at }));
        merged = [...local, ...fromServer].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      } catch { /* localStorage-only fallback is fine */ }

      if (cancelled) return;
      setTracked(merged);
      if (merged.length === 0) { setLoading(false); return; }
      loadStatuses(merged);
    })();

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, type]);

  // Auto-poll every 3s in the background while anything is still pending/processing,
  // so "Analyzing..." clears on its own instead of requiring a manual Refresh click.
  useEffect(() => {
    if (tracked.length === 0) return undefined;
    const interval = setInterval(() => {
      const stillAnalyzing = tracked.some((t) => {
        const s = statuses[t.id];
        return !s || s.pipeline_status === 'pending' || s.pipeline_status === 'processing';
      });
      if (stillAnalyzing) loadStatuses(tracked, { silent: true });
    }, 3000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tracked, statuses]);

  if (tracked.length === 0) {
    return (
      <div className="bg-white p-8 rounded-lg border border-gray-200 text-center text-sm text-gray-500">
        You haven't filed any {type === 'complaint' ? 'complaints' : 'suggestions'} yet.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <button onClick={() => loadStatuses()} className="flex items-center gap-1 text-xs text-[#0e75c6] font-semibold hover:underline">
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>
      {tracked.map((t) => {
        const s = statuses[t.id];
        const hasError = !s;
        const isAnalyzing = s && (s.pipeline_status === 'pending' || s.pipeline_status === 'processing');
        const rejected = s && s.pipeline_status === 'done' && s.is_valid_submission === false;
        const rejection = rejected ? getRejectionMessage(s.review_reason) : null;
        // Whether there's anything worth expanding for: either the AI's
        // understanding of a valid submission, or a rejection explanation.
        const canExpand = !isAnalyzing && !hasError && !!s && (s.is_valid_submission === true || rejected);
        const expanded = expandedIds.has(t.id);

        return (
          <div key={t.id} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
            <div
              className={`p-4 flex items-start justify-between gap-3 ${canExpand ? 'cursor-pointer' : ''}`}
              onClick={() => canExpand && toggleExpanded(t.id)}
            >
              <div className="min-w-0">
                <p className="text-xs text-gray-400 font-mono mb-1">{t.id}</p>
                <p className="text-sm text-black font-medium line-clamp-2">
                  {s?.extracted_issue_summary || t.preview}
                </p>
                <p className="text-[11px] text-gray-400 mt-1">
                  Filed {new Date(t.created_at).toLocaleString('en-US', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {isAnalyzing && !loading && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-blue-50 text-blue-600 border-blue-200 shrink-0">
                    <Clock className="w-3 h-3" /> Analyzing…
                  </span>
                )}
                {hasError && !loading && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-red-50 text-red-600 border-red-200 shrink-0">
                    <AlertTriangle className="w-3 h-3" /> Error
                  </span>
                )}
                {loading && (
                  <span className="text-[10px] text-gray-400 shrink-0">Loading…</span>
                )}
                {!isAnalyzing && !hasError && rejected && (
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold border shrink-0 ${rejection?.tone === 'emergency' ? 'bg-red-50 text-red-700 border-red-200' : 'bg-amber-50 text-amber-700 border-amber-200'}`}>
                    Not Registered
                  </span>
                )}
                {!isAnalyzing && !hasError && s && s.is_valid_submission === true && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-green-50 text-green-700 border-green-200 capitalize shrink-0">
                    {s.status}
                  </span>
                )}
                {!isAnalyzing && !hasError && s && s.is_valid_submission === true && !feedbackAnswered(t.id) && (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#0e75c6]" title="Feedback requested" />
                )}
                {canExpand && (
                  <button className="text-gray-400 hover:text-black transition-colors">
                    {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </button>
                )}
              </div>
            </div>

            {expanded && (
              <div className="border-t border-gray-100 bg-gray-50 p-4">
                {rejected && rejection && (
                  <div className={`flex items-start gap-2 p-2.5 rounded border ${rejection.tone === 'emergency' ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'}`}>
                    <AlertTriangle className={`w-4 h-4 shrink-0 mt-0.5 ${rejection.tone === 'emergency' ? 'text-red-500' : 'text-amber-500'}`} />
                    <p className="text-xs text-gray-700">{rejection.body}</p>
                  </div>
                )}

                {s && s.is_valid_submission === true && (
                  <ExtractionFeedbackCard
                    complaintId={t.id}
                    submissionType={t.type}
                    onFeedbackGiven={() => {
                      markFeedbackGiven(t.id);
                      setGivenIds((prev) => new Set(prev).add(t.id));
                    }}
                  />
                )}
              </div>
            )}

            {hasError && !loading && (
              <div className="mt-3 flex items-start gap-2 p-2.5 rounded border bg-gray-50 border-gray-200">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-gray-500" />
                <p className="text-xs text-gray-600">Couldn't check this submission's status. Try refreshing.</p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function CitizenDashboard({ user, onLogout }) {
  const [showModal, setShowModal]   = useState(false);
  const [activeView, setActiveView] = useState('home'); // 'home' | 'tracker-complaint' | 'tracker-suggestion'
  const displayName = `${user.first_name || ''} ${user.last_name || ''}`.trim() || user.email;

  return (
    <div className="min-h-full flex flex-col font-sans bg-[#ebf5fb]">

      {/* Logo header */}
      <div className="bg-white px-4 sm:px-8 py-2 flex justify-between items-center border-b border-gray-200 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="h-9 w-9 rounded-lg bg-[#0e75c6] flex items-center justify-center shrink-0">
            <MessageSquareText className="w-5 h-5 text-white" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-lg sm:text-xl font-bold text-black">Citizen's Portal</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right hidden sm:block">
            <p className="text-xs text-gray-500">Logged in as</p>
            <p className="text-sm font-bold text-black">{displayName}</p>
          </div>
          <button onClick={onLogout} className="flex items-center gap-1 bg-gray-100 hover:bg-gray-200 text-black text-xs px-3 py-1.5 rounded transition-colors font-semibold">
            <LogOut className="w-3.5 h-3.5" /> Logout
          </button>
        </div>
      </div>

      {/* Nav */}
      <div className="bg-[#0e75c6] text-white px-4 sm:px-8 flex items-center gap-6 text-sm font-semibold shadow-md">
        <button onClick={() => setActiveView('home')} className={`py-3 px-2 hover:bg-[#1f93ff] transition-colors ${activeView === 'home' ? 'bg-[#1f93ff]' : ''}`}><Home className="w-5 h-5"/></button>
        <button onClick={() => setActiveView('tracker-complaint')} className={`py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden sm:block ${activeView === 'tracker-complaint' ? 'bg-[#1f93ff]' : ''}`}>Track your Complaint</button>
        <button onClick={() => setActiveView('tracker-suggestion')} className={`py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden sm:block ${activeView === 'tracker-suggestion' ? 'bg-[#1f93ff]' : ''}`}>Track your Suggestion</button>
        <button className="py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden sm:block">Contact Us</button>
      </div>

      {/* Body */}
      {activeView === 'tracker-complaint' ? (
        <div className="flex-1 px-6 sm:px-12 py-10">
          <h2 className="text-lg font-bold text-black mb-4">Your Complaints</h2>
          <SubmissionTracker user={user.id} type="complaint" />
        </div>
      ) : activeView === 'tracker-suggestion' ? (
        <div className="flex-1 px-6 sm:px-12 py-10">
          <h2 className="text-lg font-bold text-black mb-4">Your Suggestions</h2>
          <SubmissionTracker user={user.id} type="suggestion" />
        </div>
      ) : (
        <div className="flex-1 px-6 sm:px-12 py-10">
          <p className="text-sm text-black mb-5">
            Welcome, <strong>{displayName}</strong>! Use the option below to submit a new complaint or suggestion.
          </p>

          <button onClick={() => setShowModal(true)}
            className="flex items-center gap-2 bg-[#0e75c6] text-white border-2 border-[#054483] rounded px-4 py-2.5 font-semibold text-sm hover:bg-[#054483] transition-colors shadow">
            <FileText className="w-4 h-4" />
            File a Complaint / Suggestion
          </button>
        </div>
      )}

      {showModal && <ChatIntake onClose={() => setShowModal(false)} user={user} />}
    </div>
  );
}
