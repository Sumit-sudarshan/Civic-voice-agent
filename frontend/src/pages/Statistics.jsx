import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, PieChart, Pie, Cell, Legend,
  AreaChart, Area,
} from 'recharts';
import { Layers, MapPin, Tag, TrendingUp, RefreshCw, Loader2, AlertTriangle, Users } from 'lucide-react';
import { fetchStatsSummary, fetchTrends } from '../api/client';
import { useRefreshToken } from '../api/invalidation';

// ── Colour palettes ────────────────────────────────────────────────────────
const URGENCY_COLORS = {
  critical: '#ef4444',   // red-500
  high:     '#f97316',   // orange-500
  medium:   '#eab308',   // yellow-500
  low:      '#9ca3af',   // gray-400
};

const CATEGORY_COLORS = {
  roads:        '#3b82f6',
  water:        '#06b6d4',
  electricity:  '#f59e0b',
  sanitation:   '#10b981',
  education:    '#8b5cf6',
  healthcare:   '#ec4899',
  safety:       '#ef4444',
  other:        '#6b7280',
};

const AREA_PALETTE = [
  '#3b82f6','#06b6d4','#10b981','#f59e0b','#ef4444',
  '#8b5cf6','#ec4899','#14b8a6','#f97316','#6366f1',
];

// ── Time range options ─────────────────────────────────────────────────────
const TIME_OPTIONS = [
  { label: '24H',  value: '24h' },
  { label: '7D',   value: '7d'  },
  { label: '15D',  value: '15d' },
  { label: '30D',  value: '30d' },
  { label: '6MO',  value: '6mo' },
  { label: '1Y',   value: '1y'  },
  { label: 'All',  value: 'all' },
];

// ── Custom tooltip ─────────────────────────────────────────────────────────
const TOOLTIP_STYLE = {
  borderRadius: '10px',
  border: '1px solid #e5e7eb',
  boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
  fontSize: '12px',
};

// ── KPI Card ───────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon: Icon, colorClass }) {
  return (
    <div className={`bg-white border border-gray-200 rounded-lg px-3 py-2.5 flex items-start gap-3 shadow-sm`}>
      <div className={`w-8 h-8 rounded-md flex items-center justify-center flex-shrink-0 ${colorClass}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="min-w-0">
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-0.5">{label}</p>
        <p className="text-xl font-black text-black leading-none">{value ?? '—'}</p>
        {sub && <p className="text-[10px] text-gray-400 mt-0.5 capitalize">{sub}</p>}
      </div>
    </div>
  );
}

// ── Chart card wrapper ────────────────────────────────────────────────────
function ChartCard({ title, children, className = '' }) {
  return (
    <div className={`bg-white border border-gray-200 rounded-lg p-4 shadow-sm ${className}`}>
      <h3 className="text-[10px] font-bold text-gray-600 uppercase tracking-wider mb-3">{title}</h3>
      {children}
    </div>
  );
}

// ── Urgency badge ──────────────────────────────────────────────────────────
function UrgencyBadge({ urgency }) {
  const colors = {
    critical: 'bg-red-50 text-red-700 border-red-200',
    high:     'bg-orange-50 text-orange-700 border-orange-200',
    medium:   'bg-yellow-50 text-yellow-700 border-yellow-200',
    low:      'bg-gray-100 text-gray-600 border-gray-200',
  };
  if (!urgency) return null;
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border capitalize ${colors[urgency] || colors.low}`}>
      {urgency}
    </span>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────
export default function Statistics() {
  const [timeRange, setTimeRange] = useState('all');
  const [trends, setTrends]       = useState(null);
  const [stats, setStats]         = useState(null);
  const [loading, setLoading]     = useState(true);
  const refreshToken              = useRefreshToken();

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([fetchTrends(timeRange), fetchStatsSummary()])
      .then(([t, s]) => { setTrends(t); setStats(s); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [timeRange]);

  useEffect(() => { load(); }, [load, refreshToken]);

  // ── Derived chart data — memoised so they don't recompute on unrelated re-renders ──
  const categoryData = useMemo(() => trends
    ? Object.entries(trends.by_category)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count)
    : [], [trends]);

  const areaData = useMemo(() => trends
    ? Object.entries(trends.by_area)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count)
    : [], [trends]);

  const urgencyData = useMemo(() => trends
    ? Object.entries(trends.by_urgency)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => {
          const order = { critical: 0, high: 1, medium: 2, low: 3 };
          return (order[a.name] ?? 9) - (order[b.name] ?? 9);
        })
    : [], [trends]);

  const trendData = useMemo(() => trends?.by_date || [], [trends]);

  // ── Skeleton loader ──
  const Skeleton = () => (
    <div className="h-full flex items-center justify-center">
      <Loader2 className="w-6 h-6 text-gray-300 animate-spin" />
    </div>
  );

  return (
    <div className="px-6 py-5 max-w-6xl mx-auto">

      {/* ── Header ── */}
      <div className="flex items-end justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold text-black mb-0.5">Analytics & Reporting</h1>
          <p className="text-xs text-gray-500">Civic issue trends across all areas and categories.</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Time range toggle */}
          <div className="flex rounded-md border border-gray-200 overflow-hidden bg-white shadow-sm">
            {TIME_OPTIONS.map(opt => (
              <button
                key={opt.value}
                onClick={() => setTimeRange(opt.value)}
                className={`px-3 py-1.5 text-[10px] font-bold tracking-wide transition-colors
                  ${timeRange === opt.value
                    ? 'bg-[#0e75c6] text-white'
                    : 'text-gray-600 hover:bg-gray-50'
                  }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <button
            onClick={load}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-gray-200 text-[10px] text-[#0e75c6] hover:bg-[#e8f4ff] transition-colors font-medium"
          >
            <RefreshCw className="w-3 h-3" />
            Refresh
          </button>
        </div>
      </div>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <KpiCard
          label="Total Complaints"
          value={stats?.total_issues ?? '…'}
          sub={`${stats?.open ?? 0} open · ${stats?.resolved ?? 0} resolved`}
          icon={Layers}
          colorClass="bg-blue-50 text-blue-600"
        />
        <KpiCard
          label="Suggestions"
          value={stats?.suggestions ?? '…'}
          sub="submitted by citizens"
          icon={TrendingUp}
          colorClass="bg-amber-50 text-amber-600"
        />
        <KpiCard
          label="Top Category"
          value={trends?.kpi_most_common_category ?? '…'}
          sub={trends ? `${trends.by_category[trends.kpi_most_common_category] ?? 0} complaints` : ''}
          icon={Tag}
          colorClass="bg-purple-50 text-purple-600"
        />
        <KpiCard
          label="Most Affected Area"
          value={trends?.kpi_most_affected_area ?? '…'}
          sub={trends ? `${trends.by_area[trends.kpi_most_affected_area] ?? 0} complaints` : ''}
          icon={MapPin}
          colorClass="bg-red-50 text-red-600"
        />
      </div>

      {/* ── Issue Volume Over Time (full-width) ── */}
      <ChartCard title={`Issue Volume Over Time${trends ? ` · ${trends.total_in_range} total` : ''}`} className="mb-6">
        <div className="h-56">
          {loading ? <Skeleton /> : trendData.length === 0 ? (
            <div className="h-full flex items-center justify-center text-gray-400 text-sm">
              No data for this time range.
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendData} margin={{ top: 4, right: 0, left: -24, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradOpen" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradResolved" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#10b981" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradInProgress" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#f59e0b" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
                <XAxis
                  dataKey="date"
                  axisLine={false} tickLine={false}
                  tick={{ fill: '#9ca3af', fontSize: 11 }}
                  tickFormatter={d => d.slice(5)} // MM-DD
                />
                <YAxis
                  axisLine={false} tickLine={false}
                  tick={{ fill: '#9ca3af', fontSize: 11 }}
                  allowDecimals={false}
                />
                <Tooltip contentStyle={TOOLTIP_STYLE} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '12px', paddingTop: '12px' }} />
                <Area type="monotone" dataKey="open"        name="Open"        stroke="#3b82f6" fill="url(#gradOpen)"       strokeWidth={2} dot={false} />
                <Area type="monotone" dataKey="in_progress" name="In Progress" stroke="#f59e0b" fill="url(#gradInProgress)"  strokeWidth={2} dot={false} />
                <Area type="monotone" dataKey="resolved"    name="Resolved"    stroke="#10b981" fill="url(#gradResolved)"    strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </ChartCard>

      {/* ── 3-column middle row ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">

        {/* Issues by Category */}
        <ChartCard title="By Category" className="lg:col-span-2">
          <div className="h-56">
            {loading ? <Skeleton /> : categoryData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-gray-400 text-sm">No data.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryData} margin={{ top: 0, right: 0, left: -28, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#9ca3af', fontSize: 11 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#9ca3af', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: '#f9fafb' }} />
                  <Bar dataKey="count" name="Issues" radius={[4, 4, 0, 0]}>
                    {categoryData.map((entry) => (
                      <Cell key={entry.name} fill={CATEGORY_COLORS[entry.name] || '#6b7280'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </ChartCard>

        {/* Urgency Distribution — fixed colours */}
        <ChartCard title="Urgency Distribution">
          <div className="h-56">
            {loading ? <Skeleton /> : urgencyData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-gray-400 text-sm">No data.</div>
            ) : (
              <div className="h-full flex flex-col items-center">
                <ResponsiveContainer width="100%" height="80%">
                  <PieChart>
                    <Pie
                      data={urgencyData}
                      cx="50%" cy="50%"
                      innerRadius={52} outerRadius={80}
                      paddingAngle={3}
                      dataKey="count"
                    >
                      {urgencyData.map((entry) => (
                        <Cell
                          key={entry.name}
                          fill={URGENCY_COLORS[entry.name] || '#9ca3af'}
                        />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={TOOLTIP_STYLE} />
                  </PieChart>
                </ResponsiveContainer>
                {/* Legend with correct colours */}
                <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-gray-600 mt-1">
                  {urgencyData.map(entry => (
                    <div key={entry.name} className="flex items-center gap-1.5">
                      <span
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: URGENCY_COLORS[entry.name] || '#9ca3af' }}
                      />
                      <span className="capitalize">{entry.name}</span>
                      <span className="text-gray-400">({entry.count})</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </ChartCard>
      </div>

      {/* ── Bottom row: Area chart + Top Recurring ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Issues by Area */}
        <ChartCard title="Issues by Area">
          <div className="h-56">
            {loading ? <Skeleton /> : areaData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-gray-400 text-sm">No data.</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={areaData} margin={{ top: 0, right: 0, left: -28, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#9ca3af', fontSize: 11 }} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#9ca3af', fontSize: 11 }} allowDecimals={false} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: '#f9fafb' }} />
                  <Bar dataKey="count" name="Issues" radius={[4, 4, 0, 0]}>
                    {areaData.map((_, i) => (
                      <Cell key={i} fill={AREA_PALETTE[i % AREA_PALETTE.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </ChartCard>

        {/* Top Recurring Issues */}
        <ChartCard title="Top Recurring Issues (all time)">
          {loading ? (
            <div className="h-56 flex items-center justify-center">
              <Loader2 className="w-6 h-6 text-gray-300 animate-spin" />
            </div>
          ) : !trends?.top_recurring?.length ? (
            <div className="h-56 flex items-center justify-center text-gray-400 text-sm">No recurring issues.</div>
          ) : (
            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {trends.top_recurring.map((issue, i) => (
                <div key={issue.id} className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors">
                  {/* Rank */}
                  <span className="text-lg font-black text-gray-200 leading-none w-6 flex-shrink-0 pt-0.5">
                    {i + 1}
                  </span>
                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-gray-800 truncate leading-snug">
                      {issue.summary}
                    </p>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <span className="text-xs text-gray-400 flex items-center gap-1">
                        <MapPin className="w-3 h-3" />{issue.area || 'Not specified'}
                      </span>
                      <span className="text-xs text-gray-400 capitalize">{issue.category}</span>
                      <UrgencyBadge urgency={issue.urgency} />
                    </div>
                  </div>
                  {/* Report count */}
                  <div className="flex items-center gap-1 flex-shrink-0 bg-white border border-gray-200 rounded-lg px-2 py-1">
                    <Users className="w-3 h-3 text-gray-500" />
                    <span className="text-xs font-bold text-gray-700">{issue.count}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </ChartCard>
      </div>
    </div>
  );
}
