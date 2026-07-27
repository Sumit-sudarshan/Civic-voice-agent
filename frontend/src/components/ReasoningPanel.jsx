import React, { useState } from 'react';
import LeaderFeedbackPrompt from './LeaderFeedbackPrompt';
import { revealPhone } from '../api/client';

// Render extracted value — if the model truly couldn't determine it, show a
// distinct styled placeholder rather than the raw "not specified" string.
function ExtractedValue({ value }) {
  if (!value || value.toLowerCase() === 'not specified') {
    return <span className="text-gray-400 italic text-[10px]">Not identified</span>;
  }
  return <span className="text-gray-900">{value}</span>;
}

// FR12: phone masked by default; a leader can reveal it, which is logged
// server-side (who/when) on every reveal.
function PhoneNumber({ complaintId, maskedPhone }) {
  const [phone, setPhone] = useState(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  if (phone) return <span className="font-medium text-gray-900">{phone}</span>;

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="font-medium text-gray-900">{maskedPhone}</span>
      <button
        onClick={async () => {
          setLoading(true);
          setFailed(false);
          try {
            const { phone } = await revealPhone(complaintId);
            setPhone(phone);
          } catch {
            setFailed(true);
          } finally {
            setLoading(false);
          }
        }}
        disabled={loading}
        className="text-[#1c7a3c] hover:underline text-[10px] font-semibold disabled:opacity-50"
      >
        {loading ? 'Revealing…' : 'Reveal'}
      </button>
      {failed && <span className="text-red-500 text-[10px]">Failed — try again</span>}
    </span>
  );
}

export default function ReasoningPanel({ issue }) {
  return (
    <div className="bg-gray-50 border-t border-gray-100 p-4 text-[11px]">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h4 className="font-semibold text-gray-900 mb-2">Original Submission</h4>
          <p className="text-gray-700 italic bg-white p-3 rounded-lg border border-gray-200 shadow-sm leading-relaxed text-[11px]">
            "{issue.raw_text}"
          </p>
          <div className="mt-3 text-[10px] text-gray-500 flex items-center gap-1 flex-wrap">
            Reported by: <span className="font-medium text-gray-900">{[issue.citizen_name, issue.citizen_last_name].filter(Boolean).join(' ')}</span> • Phone: <PhoneNumber complaintId={issue.id} maskedPhone={issue.citizen_phone} />
          </div>
        </div>
        
        <div>
          <h4 className="font-semibold text-gray-900 mb-2">AI Extraction & Reasoning</h4>
          <div className="space-y-3">
            {issue.extracted_issue_summary && (
              <div className="bg-white p-2.5 rounded border border-gray-100 flex items-start gap-2">
                <span className="text-gray-500 text-[10px] uppercase font-semibold mt-0.5 w-24 flex-shrink-0">Summary:</span>
                <span className="text-gray-900 leading-snug">{issue.extracted_issue_summary}</span>
              </div>
            )}
            <div className="bg-white p-2.5 rounded border border-gray-100 flex items-start gap-2">
              <span className="text-gray-500 text-[10px] uppercase font-semibold mt-0.5 w-24 flex-shrink-0">Location:</span>
              <ExtractedValue value={issue.extracted_location} />
            </div>
            <div className="bg-white p-2.5 rounded border border-gray-100 flex items-start gap-2">
              <span className="text-gray-500 text-[10px] uppercase font-semibold mt-0.5 w-24 flex-shrink-0">Area / Pincode:</span>
              <span className="text-gray-900">
                {issue.location_area || <span className="text-gray-400 italic text-[10px]">Not identified</span>}
                {issue.location_pincode && issue.location_pincode.toLowerCase() !== 'not specified' && (
                  <span className="text-gray-500"> · {issue.location_pincode}</span>
                )}
              </span>
            </div>
            <div className="bg-white p-2.5 rounded border border-gray-100 flex items-start gap-2">
              <span className="text-gray-500 text-[10px] uppercase font-semibold mt-0.5 w-24 flex-shrink-0">Affected People:</span>
              <ExtractedValue value={issue.extracted_affected_parties} />
            </div>
            <div className="bg-white p-2.5 rounded border border-gray-100 flex items-start gap-2">
              <span className="text-gray-500 text-[10px] uppercase font-semibold mt-0.5 w-24 flex-shrink-0">Ask:</span> 
              <ExtractedValue value={issue.extracted_ask} />
            </div>
            
            {issue.urgency_reasoning && (
              <div className="mt-3 p-3 bg-white border-l-4 border-black rounded shadow-sm">
                <span className="text-gray-500 text-[10px] uppercase font-semibold block mb-1">Urgency Reasoning</span>
                <span className="text-gray-900 leading-snug">{issue.urgency_reasoning}</span>
              </div>
            )}

            {/* Occasional, rate-limited spot-check for the leader (eval Layer 2, leader side) */}
            <LeaderFeedbackPrompt issue={issue} />
          </div>
        </div>
      </div>
    </div>
  );
}
