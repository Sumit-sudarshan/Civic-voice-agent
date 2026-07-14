import React, { useState, useEffect } from 'react';
import { Lightbulb, RefreshCw } from 'lucide-react';
import SuggestionRow from '../components/SuggestionRow';
import { fetchSuggestions } from '../api/client';
import { useRefreshToken } from '../api/invalidation';

export default function Suggestions() {
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const refreshToken = useRefreshToken();

  const load = async () => {
    setLoading(true);
    try {
      setSuggestions(await fetchSuggestions());
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Refetch on mount AND whenever a new submission invalidates the cache
  useEffect(() => { load(); }, [refreshToken]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="px-6 py-5 max-w-6xl mx-auto">
      <div className="flex justify-between items-end mb-5">
        <div>
          <h1 className="text-xl font-bold text-black mb-0.5">Suggestions</h1>
          <p className="text-xs text-gray-500">Citizen ideas for improving the community.</p>
        </div>
        <button onClick={load} className="text-[#0e75c6] hover:text-[#054483] flex items-center gap-1.5 text-xs font-medium transition-colors">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      {loading ? (
        <div className="text-center p-12 text-gray-500">Loading suggestions...</div>
      ) : suggestions.length === 0 ? (
        <div className="bg-white p-12 text-center rounded-xl border border-gray-200 shadow-sm">
          <Lightbulb className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <h3 className="text-lg font-medium text-gray-900">No suggestions yet</h3>
          <p className="text-gray-400 text-sm mt-1">Citizens haven't submitted any suggestions.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {suggestions.map(issue => (
            <SuggestionRow key={issue.id} issue={issue} />
          ))}
        </div>
      )}
    </div>
  );
}
