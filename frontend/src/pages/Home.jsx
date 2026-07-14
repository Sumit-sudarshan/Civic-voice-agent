import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  Layers, AlertCircle, CheckCircle2, MessageSquare, Lightbulb,
  MapPin, Tag, Search, Users
} from 'lucide-react';
import StatCard from '../components/StatCard';
import IssueRow from '../components/IssueRow';
import FloatingSummaryBot from '../components/FloatingSummaryBot';
import FilterBar from '../components/FilterBar';
import { fetchStatsSummary, fetchIssues } from '../api/client';
import { useRefreshToken } from '../api/invalidation';

// ── Urgency colours ────────────────────────────────────────────────────────
const URGENCY_COLOR = {
  critical: 'bg-red-100 text-red-700 border-red-200',
  high: 'bg-orange-100 text-orange-700 border-orange-200',
  medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  low: 'bg-gray-100 text-gray-600 border-gray-200',
};

const URGENCY_DOT = {
  critical: 'bg-red-500',
  high: 'bg-orange-400',
  medium: 'bg-yellow-400',
  low: 'bg-gray-400',
};

const PAGE_SIZE = 20;

// ── Top Issue card ─────────────────────────────────────────────────────────
function TopIssueCard({ issue, rank }) {
  const urgency = issue.urgency_level || 'low';
  const badge = URGENCY_COLOR[urgency] || URGENCY_COLOR.low;
  const dot = URGENCY_DOT[urgency] || URGENCY_DOT.low;
  const location = issue.extracted_location &&
    issue.extracted_location.toLowerCase() !== 'not specified'
    ? issue.extracted_location : null;

  const reportLabel = issue.report_count > 1
    ? `${issue.report_count} people`
    : '1 person';

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-sm transition-shadow">
      <div className="flex items-start gap-3">
        {/* Rank number */}
        <span className="text-2xl font-black text-gray-200 leading-none w-7 flex-shrink-0 pt-0.5">
          {rank}
        </span>
        <div className="flex-1 min-w-0">
          {/* Header row */}
          <div className="flex items-start justify-between gap-2 mb-1.5">
            <p className="text-sm font-semibold text-gray-900 leading-snug flex-1">
              {issue.extracted_issue_summary || '—'}
            </p>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className="flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium border bg-amber-50 text-amber-700 border-amber-200">
                <Users className="w-3 h-3" />
                {reportLabel}
              </span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border capitalize flex items-center gap-1 ${badge}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${dot} flex-shrink-0`} />
                {urgency}
              </span>
            </div>
          </div>
          {/* Meta row */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
            <span className="flex items-center gap-1">
              <MapPin className="w-3 h-3" />
              {location || issue.location_area || 'Location not specified'}
              {location && issue.location_area && <span className="text-gray-400">· {issue.location_area}</span>}
            </span>
            <span className="flex items-center gap-1 capitalize">
              <Tag className="w-3 h-3" />{issue.category}
            </span>
          </div>
          {/* Ask */}
          {issue.extracted_ask &&
            issue.extracted_ask.toLowerCase() !== 'not specified' && (
              <p className="text-xs text-gray-400 mt-1.5 italic truncate">
                Ask: {issue.extracted_ask}
              </p>
            )}
        </div>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function Home() {
  const [stats, setStats] = useState({
    total_issues: 0, urgent: 0, open: 0, resolved: 0, suggestions: 0,
  });
  const [topData, setTopData] = useState(null);   // { issues, total_matched }
  const [loadingTop, setLoadingTop] = useState(true);
  const [loadingStats, setLoadingStats] = useState(true);
  const [query, setQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState({ category: '', urgency: '', status: '', area: '', timeRange: '' });
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const refreshToken = useRefreshToken();
  const sentinelRef = useRef(null);

  // ── Load stat cards ──
  const loadStats = useCallback(() => {
    setLoadingStats(true);
    fetchStatsSummary()
      .then(data => { if (data) setStats(data); })
      .catch(console.error)
      .finally(() => setLoadingStats(false));
  }, []);

  // ── Load ALL issues, sorted by most recent first (no top-N cap) ──
  const loadTopIssues = useCallback((fetchArchived = false, timeRange = '') => {
    setLoadingTop(true);
    fetchIssues({ submissionType: 'complaint', archived: fetchArchived, timeRange })
      .then(data => setTopData(data))
      .catch(console.error)
      .finally(() => setLoadingTop(false));
  }, []);

  // Re-run on mount or cache invalidation
  useEffect(() => { loadStats(); }, [loadStats, refreshToken]);

  // Refetch issues when the status filter toggles between resolved and active,
  // or when the time range changes (both are server-side filters).
  useEffect(() => {
    loadTopIssues(filters.status === 'resolved', filters.timeRange);
  }, [loadTopIssues, refreshToken, filters.status, filters.timeRange]);

  // Reset how many rows are revealed whenever the underlying set or filters change
  useEffect(() => { setVisibleCount(PAGE_SIZE); }, [topData, query, filters]);

  const filteredIssues = topData?.issues?.filter(issue => {
    // 1. Search Query
    if (query) {
      const q = query.toLowerCase();
      const matchesSearch = (issue.extracted_issue_summary || '').toLowerCase().includes(q) ||
                            (issue.raw_text || '').toLowerCase().includes(q) ||
                            (issue.extracted_location || '').toLowerCase().includes(q);
      if (!matchesSearch) return false;
    }
    // 2. Dropdown Filters — no defaults applied beyond what the user picks
    if (filters.category && issue.category !== filters.category) return false;
    if (filters.urgency && issue.urgency_level !== filters.urgency) return false;
    if (filters.status && issue.status !== filters.status) return false;
    if (filters.area && !(issue.location_area || '').toLowerCase().includes(filters.area.toLowerCase())) return false;

    return true;
  }) || [];

  const visibleIssues = filteredIssues.slice(0, visibleCount);

  // Infinite scroll: reveal more already-fetched rows as the sentinel comes into view
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        setVisibleCount(v => Math.min(v + PAGE_SIZE, filteredIssues.length));
      }
    }, { rootMargin: '200px' });
    observer.observe(node);
    return () => observer.disconnect();
  }, [filteredIssues.length]);

  const handleFilterChange = (key, value) => setFilters({ ...filters, [key]: value });
  const clearFilters = () => {
    setFilters({ category: '', urgency: '', status: '', area: '', timeRange: '' });
    setQuery('');
  };
  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  return (
    <div className="px-6 py-5 max-w-6xl mx-auto">
      {/* ── Header ── */}
      <div className="mb-4">
        <h1 className="text-xl font-bold text-black mb-0.5">Welcome back Sumit</h1>
        <p className="text-xs text-gray-500">Here's what's happening across your area today.</p>
      </div>

      {/* ── Stat cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5 mb-5">
        <StatCard title="Total" value={loadingStats ? undefined : stats.total_issues} icon={Layers} colorClass="bg-gray-100 text-gray-700" />
        <StatCard title="Critical" value={loadingStats ? undefined : stats.critical} icon={AlertCircle} colorClass="bg-red-50 text-red-600" />
        <StatCard title="Open" value={loadingStats ? undefined : stats.open} icon={MessageSquare} colorClass="bg-[#e8f4ff] text-[#0e75c6]" />
        <StatCard title="Resolved" value={loadingStats ? undefined : stats.resolved} icon={CheckCircle2} colorClass="bg-green-50 text-green-600" />
        <StatCard title="Suggestions" value={loadingStats ? undefined : stats.suggestions} icon={Lightbulb} colorClass="bg-orange-50 text-orange-600" />
      </div>

      {/* ── Search and Filters inline ── */}
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search issues..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl shadow-sm text-sm focus:outline-none focus:ring-2 focus:ring-black/5"
          />
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`px-5 py-2.5 border rounded-xl shadow-sm text-sm font-medium transition-colors ${showFilters || activeFilterCount > 0
              ? 'bg-[#0e75c6] text-white border-[#0e75c6]'
              : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
            }`}
        >
          Filters {activeFilterCount > 0 && `(${activeFilterCount})`}
        </button>
      </div>

      {showFilters && (
        <FilterBar
          filters={filters}
          onChange={handleFilterChange}
          onClear={clearFilters}
          showUrgency={true}
        />
      )}

      {/* ── Layout: Top Issues ── */}
      <div className="w-full">
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-bold text-black uppercase tracking-wider">All Issues</h2>
            {topData && (
              <span className="text-xs text-gray-400">
                {filteredIssues.length} total · showing {visibleIssues.length}
              </span>
            )}
          </div>

          {loadingTop ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="bg-white border border-gray-200 rounded-xl p-4 animate-pulse">
                  <div className="h-4 bg-gray-100 rounded w-3/4 mb-2" />
                  <div className="h-3 bg-gray-100 rounded w-1/2" />
                </div>
              ))}
            </div>
          ) : filteredIssues.length === 0 ? (
            <div className="bg-white p-10 text-center rounded-xl border border-gray-200 shadow-sm">
              <CheckCircle2 className="w-10 h-10 text-gray-200 mx-auto mb-3" />
              <h3 className="text-sm font-bold text-gray-900">No issues found</h3>
              <p className="text-gray-400 text-xs mt-1">Try a different search or filter.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {visibleIssues.map((issue, i) => (
                <IssueRow key={issue.id} issue={issue} index={i + 1} />
              ))}
              {/* Infinite-scroll sentinel — reveals more already-fetched rows as it comes into view */}
              {visibleCount < filteredIssues.length && (
                <div ref={sentinelRef} className="py-4 text-center text-xs text-gray-400">
                  Loading more…
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <FloatingSummaryBot />
    </div>
  );
}
