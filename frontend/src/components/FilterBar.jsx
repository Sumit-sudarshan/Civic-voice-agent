import React from 'react';
import { SlidersHorizontal, X } from 'lucide-react';

const CATEGORIES = ['roads', 'water', 'electricity', 'sanitation', 'education', 'healthcare', 'safety', 'other'];
const URGENCY_LEVELS = ['critical', 'high', 'medium', 'low'];
const STATUSES = ['open', 'in_progress', 'resolved'];
// Same values as FloatingSummaryBot's time selector and the backend's
// /stats cutoff convention, so "7D" means the identical window everywhere.
const TIME_RANGES = [
  { label: '24H', value: '24h' },
  { label: '7D',  value: '7d' },
  { label: '15D', value: '15d' },
  { label: '1M',  value: '30d' },
  { label: '6M',  value: '6mo' },
  { label: '1Y',  value: '1y' },
];

/**
 * Reusable filter bar for the Complaints (and optionally Suggestions) page.
 * Props:
 *   filters: { category, urgency, status, area }
 *   onChange(key, value): called on every filter change
 *   onClear(): called when the X is clicked
 *   showUrgency: bool — hide urgency filter on Suggestions page
 */
export default function FilterBar({ filters = {}, onChange, onClear, showUrgency = true }) {
  const activeCount = Object.values(filters).filter(Boolean).length;

  return (
    <div className="bg-white p-3 rounded-lg border border-gray-200 shadow-sm mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
          <SlidersHorizontal className="w-4 h-4" />
          Filters {activeCount > 0 && <span className="bg-[#1c7a3c] text-white rounded-full px-2 py-0.5 text-xs">{activeCount}</span>}
        </div>
        {activeCount > 0 && (
          <button onClick={onClear} className="text-gray-400 hover:text-black transition-colors flex items-center gap-1 text-xs">
            <X className="w-3 h-3" /> Clear all
          </button>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Category</label>
          <select
            value={filters.category || ''}
            onChange={(e) => onChange('category', e.target.value)}
            className="w-full px-2 py-1.5 border border-gray-200 rounded-lg bg-white text-xs capitalize focus:outline-none focus:border-[#1c7a3c] focus:ring-1 focus:ring-[#1c7a3c]"
          >
            <option value="">All</option>
            {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        {showUrgency && (
          <div>
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Urgency</label>
            <select
              value={filters.urgency || ''}
              onChange={(e) => onChange('urgency', e.target.value)}
              className="w-full px-2 py-1.5 border border-gray-200 rounded-lg bg-white text-xs capitalize focus:outline-none focus:border-[#1c7a3c] focus:ring-1 focus:ring-[#1c7a3c]"
            >
              <option value="">All</option>
              {URGENCY_LEVELS.map(u => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
        )}

        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Status</label>
          <select
            value={filters.status || ''}
            onChange={(e) => onChange('status', e.target.value)}
            className="w-full px-2 py-1.5 border border-gray-200 rounded-lg bg-white text-xs capitalize focus:outline-none focus:border-[#1c7a3c] focus:ring-1 focus:ring-[#1c7a3c]"
          >
            <option value="">All</option>
            {STATUSES.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Area</label>
          <input
            type="text"
            value={filters.area || ''}
            onChange={(e) => onChange('area', e.target.value)}
            placeholder="e.g. Cotton Green"
            className="w-full px-2 py-1.5 border border-gray-200 rounded-lg bg-white text-xs focus:outline-none focus:border-[#1c7a3c] focus:ring-1 focus:ring-[#1c7a3c]"
          />
        </div>

        <div>
          <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Time Range</label>
          <select
            value={filters.timeRange || ''}
            onChange={(e) => onChange('timeRange', e.target.value)}
            className="w-full px-2 py-1.5 border border-gray-200 rounded-lg bg-white text-xs focus:outline-none focus:border-[#1c7a3c] focus:ring-1 focus:ring-[#1c7a3c]"
          >
            <option value="">All time</option>
            {TIME_RANGES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}
