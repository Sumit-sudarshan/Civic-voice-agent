import React, { useState, memo } from 'react';
import { AlertTriangle, MapPin, Users, ChevronDown, ChevronUp, Loader2, CheckCircle2, Clock, RotateCcw } from 'lucide-react';
import ReasoningPanel from './ReasoningPanel';
import Toast from './Toast';
import { updateComplaintStatus } from '../api/client';
import { invalidateComplaints } from '../api/invalidation';

const urgencyColors = {
  critical: 'bg-red-50 text-red-700 border-red-200',
  high:     'bg-orange-50 text-orange-700 border-orange-200',
  medium:   'bg-yellow-50 text-yellow-700 border-yellow-200',
  low:      'bg-gray-50 text-gray-700 border-gray-200',
};

const statusColors = {
  open:        'bg-gray-100 text-gray-800 border-gray-200',
  in_progress: 'bg-[#e8f4ff] text-[#0e75c6] border-[#bae0ff]',
  resolved:    'bg-green-50 text-green-700 border-green-200',
};

const STATUS_LABELS = {
  open:        'Open',
  in_progress: 'In Progress',
  resolved:    'Resolved',
};

function IssueRow({ issue, index }) {
  const [expanded, setExpanded]         = useState(false);
  const [localStatus, setLocalStatus]   = useState(issue.status);
  const [loading, setLoading]           = useState(false);
  const [confirmResolve, setConfirmResolve] = useState(false);
  const [toast, setToast]               = useState(null);

  const isAnalyzing = issue.pipeline_status === 'pending' || issue.pipeline_status === 'processing';

  const reportLabel = issue.report_count > 1
    ? `${issue.report_count} people`
    : '1 person';

  const changeStatus = async (newStatus) => {
    setLoading(true);
    setConfirmResolve(false);
    try {
      setLocalStatus(newStatus);
      await updateComplaintStatus(issue.id, newStatus);
      invalidateComplaints();
      setToast({ message: `Marked as ${STATUS_LABELS[newStatus]}`, type: 'success' });
    } catch (err) {
      setLocalStatus(issue.status);
      setToast({ message: 'Failed to update status. Try again.', type: 'error' });
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="border border-gray-200 bg-white rounded-lg mb-2 overflow-hidden shadow-sm hover:shadow transition-shadow">
        {/* ── Collapsed row ── */}
        <div
          className="px-4 py-3 flex items-center justify-between cursor-pointer"
          onClick={() => setExpanded(!expanded)}
        >
          {/* Left: icon + title + meta */}
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <div className={`w-8 h-8 rounded-md flex items-center justify-center border flex-shrink-0 ${
              isAnalyzing ? 'bg-blue-50 border-blue-200' : 'bg-gray-50 border-gray-200'
            }`}>
              {isAnalyzing
                ? <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
                : <span className="font-bold text-gray-700 text-[13px]">{index}</span>
              }
            </div>
            <div className="min-w-0">
              <h4 className="font-semibold text-gray-900 text-[13px] leading-tight truncate">
                {issue.extracted_issue_summary || (isAnalyzing ? 'Analyzing submission…' : issue.raw_text)}
              </h4>
              <div className="flex items-center gap-2 text-[11px] text-gray-500 mt-1 flex-wrap">
                <span className="flex items-center gap-1">
                  <MapPin className="w-3 h-3" />{issue.location_area || 'Not specified'}
                </span>
                <span className="capitalize px-1.5 py-0.5 bg-gray-100 rounded border border-gray-200 leading-none">
                  {issue.category}
                </span>
                <span className="flex items-center gap-1 ml-1 text-gray-400 font-medium">
                  <Clock className="w-3 h-3" />
                  {new Date(issue.created_at).toLocaleString('en-US', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            </div>
          </div>

          {/* Right: badges + chevron */}
          <div className="flex items-center gap-2 flex-shrink-0 ml-4">
            {isAnalyzing ? (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-blue-50 text-blue-600 border-blue-200 flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" /> Analyzing…
              </span>
            ) : (
              <>
                <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-amber-50 text-amber-700 border-amber-200 leading-none">
                  <Users className="w-3 h-3" />
                  {reportLabel}
                </span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold capitalize border leading-none ${
                  urgencyColors[issue.urgency_level] || urgencyColors.low
                }`}>
                  {issue.urgency_level || 'Low'}
                </span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold capitalize border leading-none ${
                  statusColors[localStatus] || statusColors.open
                }`}>
                  {STATUS_LABELS[localStatus] || localStatus}
                </span>
              </>
            )}
            <button className="text-gray-400 hover:text-black transition-colors ml-1">
              {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* ── Expanded: AI extraction + leader actions ── */}
        {expanded && (
          <>
            <ReasoningPanel issue={issue} />

            {/* Leader action bar */}
            {!isAnalyzing && issue.is_valid_submission === true && (
              <div className="border-t border-gray-100 px-4 py-2 bg-gray-50 flex items-center gap-2 flex-wrap">
                <span className="text-[10px] text-gray-500 font-bold uppercase tracking-wider mr-1">Actions:</span>

                {localStatus === 'open' && (
                  <button
                    onClick={() => changeStatus('in_progress')}
                    disabled={loading}
                    className="flex items-center gap-1 px-2.5 py-1 rounded border border-[#bae0ff] text-[#0e75c6] bg-[#e8f4ff] hover:bg-[#d6ebff] text-[10px] font-semibold disabled:opacity-50 transition-colors"
                  >
                    <Clock className="w-3 h-3" />
                    Mark In Progress
                  </button>
                )}

                {localStatus !== 'resolved' && !confirmResolve && (
                  <button
                    onClick={(e) => { e.stopPropagation(); setConfirmResolve(true); }}
                    disabled={loading}
                    className="flex items-center gap-1 px-2.5 py-1 rounded border border-green-200 text-green-700 bg-green-50 hover:bg-green-100 text-[10px] font-semibold disabled:opacity-50 transition-colors"
                  >
                    <CheckCircle2 className="w-3 h-3" />
                    Mark Resolved
                  </button>
                )}

                {confirmResolve && (
                  <span className="flex items-center gap-1.5">
                    <span className="text-[10px] text-gray-500 font-medium">Are you sure?</span>
                    <button
                      onClick={() => changeStatus('resolved')}
                      disabled={loading}
                      className="px-2.5 py-1 rounded bg-green-600 text-white hover:bg-green-700 text-[10px] font-bold disabled:opacity-50 transition-colors"
                    >
                      Yes, Resolve
                    </button>
                    <button
                      onClick={() => setConfirmResolve(false)}
                      className="px-2.5 py-1 rounded text-gray-500 hover:text-black text-[10px] font-semibold transition-colors"
                    >
                      Cancel
                    </button>
                  </span>
                )}

                {localStatus === 'resolved' && (
                  <button
                    onClick={() => changeStatus('open')}
                    disabled={loading}
                    className="flex items-center gap-1 px-2.5 py-1 rounded border border-gray-200 text-gray-700 bg-gray-100 hover:bg-gray-200 text-[10px] font-semibold disabled:opacity-50 transition-colors"
                  >
                    <RotateCcw className="w-3 h-3" />
                    Reopen
                  </button>
                )}

                {loading && (
                  <Loader2 className="w-3 h-3 text-gray-400 animate-spin ml-1" />
                )}
              </div>
            )}
          </>
        )}
      </div>

      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    </>
  );
}

export default memo(IssueRow);
