import React, { useState, useEffect } from 'react';
import { Sparkles, X, ChevronLeft, Loader2, RefreshCw } from 'lucide-react';
import { fetchSummaryReport } from '../api/client';

const TIME_OPTIONS = [
  { label: '24H', value: '24h' },
  { label: '7D',  value: '7d' },
  { label: '15D', value: '15d' },
  { label: '1M',  value: '30d' },
  { label: '6M',  value: '6mo' },
  { label: '1Y',  value: '1y' },
];

// Renders the report's minimal markup: a line that is entirely **bold** is a
// section header, and any inline **span** within a line is bolded — the only
// two conventions app/llm/prompts/summarize.py's render_report relies on.
function renderReportText(report) {
  return report.split('\n').map((line, i) => {
    if (line.trim() === '') return <div key={i} className="h-2" />;

    const isHeader = /^\*\*[^*]+\*\*$/.test(line.trim());
    const parts = line.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
    const rendered = parts.map((part, j) =>
      part.startsWith('**') && part.endsWith('**')
        ? <strong key={j} className="font-bold text-gray-900">{part.slice(2, -2)}</strong>
        : <React.Fragment key={j}>{part}</React.Fragment>
    );

    return (
      <div
        key={i}
        className={isHeader
          ? 'text-xs font-bold uppercase tracking-wider text-gray-800 mt-3 mb-1 first:mt-0'
          : 'leading-relaxed'}
      >
        {rendered}
      </div>
    );
  });
}

function SummaryPanel({ submissionType, timeRange, refreshSignal }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = (refresh = false) => {
    setLoading(true);
    fetchSummaryReport({ timeRange, submissionType, refresh })
      .then(data => setReport(data.report))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timeRange, submissionType, refreshSignal]);

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
      {loading ? (
        <div className="flex flex-col items-center justify-center min-h-40 gap-3 py-6">
          <Loader2 className="w-6 h-6 text-gray-400 animate-spin" />
          <p className="text-sm text-gray-500">Generating briefing…</p>
          <p className="text-xs text-gray-400">This may take 30–60 seconds on first load.</p>
        </div>
      ) : !report ? (
        <div className="text-center text-gray-400 text-sm min-h-40 flex items-center justify-center">
          No data to summarise for this time range.
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-4 h-4 text-amber-500" />
            <span className="text-xs font-bold text-gray-700 uppercase tracking-wider">AI Briefing</span>
          </div>
          <div className="text-sm text-gray-700 font-sans">
            {renderReportText(report)}
          </div>
        </>
      )}
    </div>
  );
}

export default function FloatingSummaryBot() {
    const [isOpen, setIsOpen] = useState(false);
    const [view, setView] = useState('menu'); // 'menu', 'issues', 'suggestions'
    const [timeRange, setTimeRange] = useState('7d');
    const [refreshSignal, setRefreshSignal] = useState(0);

    if (!isOpen) {
        return (
            <button
                onClick={() => setIsOpen(true)}
                className="fixed bottom-8 right-8 bg-[#0e75c6] text-white px-5 py-4 rounded-full shadow-2xl hover:bg-[#054483] hover:scale-105 transition-all flex items-center gap-2.5 font-medium z-50 border border-[#054483]"
            >
                <Sparkles className="w-5 h-5 text-amber-300" />
                <span className="hidden sm:inline tracking-wide">AI Summary</span>
            </button>
        );
    }

    return (
        <div className="fixed bottom-8 right-8 w-80 sm:w-[420px] bg-white border border-gray-200 rounded-2xl shadow-2xl flex flex-col overflow-hidden z-50 animate-in slide-in-from-bottom-5 fade-in duration-200">
            {/* Header */}
            <div className="bg-[#0e75c6] text-white px-5 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    {view !== 'menu' && (
                        <button onClick={() => setView('menu')} className="text-[#7ec8f7] hover:text-white transition-colors p-1 -ml-2 rounded-full hover:bg-white/10">
                            <ChevronLeft className="w-5 h-5" />
                        </button>
                    )}
                    <Sparkles className="w-4 h-4 text-amber-300" />
                    <span className="font-semibold text-sm tracking-wide">AI Summary Assistant</span>
                </div>
                <button onClick={() => { setIsOpen(false); setView('menu'); }} className="text-[#7ec8f7] hover:text-white transition-colors p-1 -mr-2 rounded-full hover:bg-white/10">
                    <X className="w-5 h-5" />
                </button>
            </div>

            {/* Time range selector — always visible, pick it before or after choosing a summary */}
            <div className="px-5 py-3 bg-white border-b border-gray-100 flex items-center justify-between gap-2 flex-wrap">
                <div className="flex rounded-md border border-gray-200 overflow-hidden bg-white shadow-sm">
                    {TIME_OPTIONS.map(opt => (
                        <button
                            key={opt.value}
                            onClick={() => setTimeRange(opt.value)}
                            className={`px-2 py-1 text-[10px] font-bold tracking-wide transition-colors
                                ${timeRange === opt.value ? 'bg-[#0e75c6] text-white' : 'text-gray-600 hover:bg-gray-50'}`}
                        >
                            {opt.label}
                        </button>
                    ))}
                </div>
                {view !== 'menu' && (
                    <button
                        onClick={() => setRefreshSignal(s => s + 1)}
                        className="flex items-center gap-1 text-xs text-gray-500 hover:text-black transition-colors px-2 py-1 rounded-lg hover:bg-gray-50"
                    >
                        <RefreshCw className="w-3 h-3" /> Refresh
                    </button>
                )}
            </div>

            {/* Body */}
            <div className="p-5 bg-gray-50 flex-1 overflow-y-auto max-h-[70vh] min-h-[350px]">
                {view === 'menu' && (
                    <div className="flex flex-col gap-3 mt-2">
                        <p className="text-sm text-gray-600 mb-1 leading-relaxed">Hello! I'm your AI assistant. Pick a time range above, then choose what to summarise.</p>

                        <button
                            onClick={() => setView('issues')}
                            className="bg-white border border-gray-200 rounded-xl p-5 text-left hover:border-[#0e75c6] hover:shadow-md transition-all flex items-center justify-between group"
                        >
                            <div>
                                <h4 className="font-semibold text-gray-900 text-sm mb-1">Summary for issues</h4>
                                <p className="text-xs text-gray-500 leading-relaxed">An actionable briefing on current citizen complaints across your chosen time range.</p>
                            </div>
                        </button>

                        <button
                            onClick={() => setView('suggestions')}
                            className="bg-white border border-gray-200 rounded-xl p-5 text-left hover:border-[#0e75c6] hover:shadow-md transition-all flex items-center justify-between group"
                        >
                            <div>
                                <h4 className="font-semibold text-gray-900 text-sm mb-1">Summary for suggestions</h4>
                                <p className="text-xs text-gray-500 leading-relaxed">What citizens are proposing to improve your area, and what's gaining the most support.</p>
                            </div>
                        </button>
                    </div>
                )}

                {view === 'issues' && <SummaryPanel submissionType="complaint" timeRange={timeRange} refreshSignal={refreshSignal} />}
                {view === 'suggestions' && <SummaryPanel submissionType="suggestion" timeRange={timeRange} refreshSignal={refreshSignal} />}
            </div>
        </div>
    );
}
