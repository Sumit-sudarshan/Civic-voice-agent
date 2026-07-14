import React, { useState, useEffect, useCallback } from 'react';
import { Search, RefreshCw } from 'lucide-react';
import { fetchComplaints } from '../api/client';
import { useRefreshToken } from '../api/invalidation';
import { useDebounce } from '../api/useDebounce';
import IssueRow from '../components/IssueRow';
import FilterBar from '../components/FilterBar';

// Reusable skeleton card that mirrors IssueRow's collapsed height
function SkeletonRow() {
  return (
    <div className="border border-gray-100 bg-white rounded-xl p-4 flex items-center gap-4 animate-pulse">
      <div className="w-10 h-10 rounded-full bg-gray-100 flex-shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-4 bg-gray-100 rounded w-2/3" />
        <div className="h-3 bg-gray-100 rounded w-1/3" />
      </div>
      <div className="h-6 w-16 bg-gray-100 rounded-full" />
      <div className="h-6 w-16 bg-gray-100 rounded-full" />
    </div>
  );
}

export default function Complaints() {
  const [complaints, setComplaints] = useState([]);
  const [loading, setLoading]       = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [query, setQuery]           = useState('');
  const [filters, setFilters]       = useState({ category: '', urgency: '', status: '', area: '', timeRange: '' });

  const refreshToken   = useRefreshToken();
  const debouncedQuery = useDebounce(query, 300);

  const load = useCallback(async (q, f = filters) => {
    setLoading(true);
    try {
      const params = {};
      if (q)          params.q = q;
      if (f.category) params.category = f.category;
      if (f.urgency)  params.urgency = f.urgency;
      if (f.status)    params.status = f.status;
      if (f.area)      params.area = f.area;
      if (f.timeRange) params.timeRange = f.timeRange;
      setComplaints(await fetchComplaints(params));
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fire when debounced query changes (300ms after typing stops)
  useEffect(() => {
    load(debouncedQuery, filters);
  }, [debouncedQuery, refreshToken]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll every 8s while any complaint is still being analyzed
  useEffect(() => {
    const hasAnalyzing = complaints.some(
      c => c.pipeline_status === 'pending' || c.pipeline_status === 'processing'
    );
    if (!hasAnalyzing) return;
    const interval = setInterval(() => load(debouncedQuery, filters), 8000);
    return () => clearInterval(interval);
  }, [complaints]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFilterChange = (key, value) => {
    const next = { ...filters, [key]: value };
    setFilters(next);
    load(debouncedQuery, next);
  };

  const clearFilters = () => {
    const cleared = { category: '', urgency: '', status: '', area: '', timeRange: '' };
    setFilters(cleared);
    setQuery('');
    load('', cleared);
  };

  const activeFilterCount = Object.values(filters).filter(Boolean).length;

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-3xl font-bold text-black mb-2">Complaints</h1>
          <p className="text-gray-500">Manage and resolve citizen issues across all areas.</p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => load(debouncedQuery, filters)}
            className="text-gray-500 hover:text-black flex items-center gap-2 text-sm transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Search and Filters inline */}
      <div className="flex gap-3 mb-4">
        <div className="flex-1 bg-white p-2.5 rounded-xl border border-gray-200 shadow-sm relative flex items-center">
          <Search className="w-4 h-4 absolute left-3.5 text-gray-400" />
          <input
            type="text"
            placeholder="Search complaints… (results update as you type)"
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="w-full pl-9 pr-4 bg-transparent focus:outline-none text-sm transition-colors"
          />
        </div>
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`px-5 py-2.5 border rounded-xl shadow-sm text-sm font-medium transition-colors ${
            activeFilterCount > 0
              ? 'bg-black text-white border-black'
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

      {/* Skeleton while loading, real list when ready */}
      {loading ? (
        <div className="space-y-3">
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      ) : complaints.length === 0 ? (
        <div className="bg-white p-12 text-center rounded-xl border border-gray-200 shadow-sm">
          <Search className="w-12 h-12 text-gray-200 mx-auto mb-3" />
          <h3 className="text-lg font-medium text-gray-900">No complaints found</h3>
          <p className="text-gray-400 text-sm mt-1">Try adjusting your search or filters.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {complaints.map(issue => <IssueRow key={issue.id} issue={issue} />)}
        </div>
      )}
    </div>
  );
}
