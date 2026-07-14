import React from 'react';

export default function StatCard({ title, value, icon: Icon, colorClass }) {
  const isLoading = value === undefined || value === null;

  return (
    <div className="bg-white px-3 py-2.5 rounded-lg border border-gray-200 flex items-center gap-2.5 shadow-sm">
      <div className={`p-1.5 rounded-md ${colorClass} flex-shrink-0`}>
        <Icon className="w-3.5 h-3.5" />
      </div>
      <div>
        <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider leading-none mb-0.5">
          {title}
        </p>
        {isLoading ? (
          <div className="h-4 w-8 bg-gray-100 animate-pulse rounded mt-0.5" />
        ) : (
          <h3 className="text-lg font-bold text-black leading-none">{value}</h3>
        )}
      </div>
    </div>
  );
}
