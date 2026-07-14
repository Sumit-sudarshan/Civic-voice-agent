import React, { useState, memo } from 'react';
import { Lightbulb, MapPin, Users, ChevronDown, ChevronUp } from 'lucide-react';
import ReasoningPanel from './ReasoningPanel';

const statusColors = {
  open: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  in_progress: 'bg-[#e8f4ff] text-[#0e75c6] border-[#bae0ff]',
  resolved: 'bg-gray-100 text-gray-600 border-gray-200',
};

function SuggestionRow({ issue }) {
  const [expanded, setExpanded] = useState(false);

  const reportLabel = issue.report_count > 1
    ? `${issue.report_count} supporters`
    : '1 person';

  return (
    <div className="border border-gray-200 bg-white rounded-lg mb-2 overflow-hidden shadow-sm hover:shadow transition-shadow">
      <div
        className="px-4 py-3 flex items-center justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        {/* Left: icon + summary + meta */}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="w-8 h-8 rounded-md flex items-center justify-center bg-amber-50 border border-amber-200 flex-shrink-0">
            <Lightbulb className="w-4 h-4 text-amber-500" />
          </div>
          <div className="min-w-0">
            <h4 className="font-semibold text-gray-900 text-[13px] leading-tight truncate">
              {issue.extracted_issue_summary || issue.raw_text}
            </h4>
            <div className="flex items-center gap-2 text-[11px] text-gray-500 mt-1 flex-wrap">
              <span className="flex items-center gap-1">
                <MapPin className="w-3 h-3" />{issue.location_area || 'Not specified'}
              </span>
              <span className="capitalize px-1.5 py-0.5 bg-gray-100 rounded border border-gray-200 leading-none">
                {issue.category}
              </span>
            </div>
          </div>
        </div>

        {/* Right: supporter count + status + chevron */}
        <div className="flex items-center gap-2 flex-shrink-0 ml-4">
          <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-amber-50 text-amber-700 border-amber-200 leading-none">
            <Users className="w-3 h-3" />
            {reportLabel}
          </span>
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold capitalize border leading-none ${statusColors[issue.status] || statusColors.open}`}>
            {issue.status.replace('_', ' ')}
          </span>
          <button className="text-gray-400 hover:text-black transition-colors ml-1">
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {expanded && <ReasoningPanel issue={issue} />}
    </div>
  );
}

export default memo(SuggestionRow);
