import React, { useState, useEffect } from 'react';
import { Home, LogOut, FileText, AlertTriangle, Clock, RefreshCw, MessageSquareText } from 'lucide-react';
import { fetchSubmissionStatus } from '../api/client';
import { getRejectionMessage } from '../api/rejectionMessages';
import { getTrackedSubmissions, removeTrackedSubmissions } from '../api/trackedSubmissions';
import { getIdentity } from '../api/identity';
import ChatIntake from './ChatIntake';

function SubmissionTracker({ user, type }) {
  const [tracked, setTracked]   = useState(() => getTrackedSubmissions(user).filter(t => t.type === type));
  const [statuses, setStatuses] = useState({}); // id -> live submission record
  const [loading, setLoading]   = useState(true);

  const loadStatuses = async (list = tracked) => {
    setLoading(true);
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
    setLoading(false);
  };

  useEffect(() => {
    const filtered = getTrackedSubmissions(user).filter(t => t.type === type);
    setTracked(filtered);
    if (filtered.length === 0) { setLoading(false); return; }
    loadStatuses(filtered);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, type]);

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

        return (
          <div key={t.id} className="bg-white border border-gray-200 rounded-lg p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs text-gray-400 font-mono mb-1">{t.id}</p>
                <p className="text-sm text-black font-medium truncate">
                  {s?.extracted_issue_summary || t.preview}
                </p>
                <p className="text-[11px] text-gray-400 mt-1">
                  Filed {new Date(t.created_at).toLocaleString('en-US', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>

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
            </div>

            {!isAnalyzing && !hasError && rejected && rejection && (
              <div className={`mt-3 flex items-start gap-2 p-2.5 rounded border ${rejection.tone === 'emergency' ? 'bg-red-50 border-red-200' : 'bg-amber-50 border-amber-200'}`}>
                <AlertTriangle className={`w-4 h-4 shrink-0 mt-0.5 ${rejection.tone === 'emergency' ? 'text-red-500' : 'text-amber-500'}`} />
                <p className="text-xs text-gray-700">{rejection.body}</p>
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
  // `user` (the login ID, e.g. "CivicAgent") stays the localStorage/tracking
  // key throughout — only the display name shown to the citizen changes.
  const identity = getIdentity();
  const displayName = `${identity.firstName} ${identity.lastName}`;

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
          <SubmissionTracker user={user} type="complaint" />
        </div>
      ) : activeView === 'tracker-suggestion' ? (
        <div className="flex-1 px-6 sm:px-12 py-10">
          <h2 className="text-lg font-bold text-black mb-4">Your Suggestions</h2>
          <SubmissionTracker user={user} type="suggestion" />
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
