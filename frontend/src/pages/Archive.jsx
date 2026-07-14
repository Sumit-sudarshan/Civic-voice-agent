import React, { useEffect, useState, useCallback } from 'react';
import { Archive as ArchiveIcon } from 'lucide-react';
import IssueRow from '../components/IssueRow';
import { fetchIssues } from '../api/client';
import { useRefreshToken } from '../api/invalidation';

export default function Archive() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const refreshToken = useRefreshToken();

  const load = useCallback(() => {
    setLoading(true);
    fetchIssues({ submissionType: 'complaint', archived: true })
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load, refreshToken]);

  const issues = data?.issues || [];

  return (
    <div className="px-6 py-5 max-w-6xl mx-auto">
      <div className="mb-4">
        <h1 className="text-xl font-bold text-black mb-0.5">Archive</h1>
        <p className="text-xs text-gray-500">Resolved issues, moved out of the active dashboard automatically.</p>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="bg-white border border-gray-200 rounded-xl p-4 animate-pulse">
              <div className="h-4 bg-gray-100 rounded w-3/4 mb-2" />
              <div className="h-3 bg-gray-100 rounded w-1/2" />
            </div>
          ))}
        </div>
      ) : issues.length === 0 ? (
        <div className="bg-white p-10 text-center rounded-xl border border-gray-200 shadow-sm">
          <ArchiveIcon className="w-10 h-10 text-gray-200 mx-auto mb-3" />
          <h3 className="text-sm font-bold text-gray-900">No archived issues yet</h3>
          <p className="text-gray-400 text-xs mt-1">Resolved issues will show up here.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {issues.map((issue, i) => (
            <IssueRow key={issue.id} issue={issue} index={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}
