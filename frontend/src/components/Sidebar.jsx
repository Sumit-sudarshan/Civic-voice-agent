import React from 'react';
import { Home, Lightbulb, BarChart2, Settings, LogOut, MessageSquareText, Archive } from 'lucide-react';

export default function Sidebar({ active, setActive, leaderName, onLogout }) {
  const navItems = [
    { id: 'home', label: 'Overview', icon: Home },
    { id: 'suggestions', label: 'Suggestions', icon: Lightbulb },
    { id: 'statistics', label: 'Statistics', icon: BarChart2 },
    { id: 'archive', label: 'Archive', icon: Archive },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <div className="w-56 shrink-0 bg-[#123c22] text-white flex flex-col relative shadow-xl z-50">
      {/* Brand */}
      <div className="px-4 py-4 flex items-center gap-2.5 border-b border-white/10">
        <div className="h-10 w-10 rounded-lg bg-[#25963f] flex items-center justify-center shrink-0">
          <MessageSquareText className="w-5 h-5 text-white" />
        </div>
        <span className="text-sm font-bold tracking-wide leading-tight">Civic Voice<br />
          <span className="text-[#8fd6a3] font-medium text-xs">Portal</span>
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActive(item.id)}
            className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-xs font-medium transition-all ${active === item.id
              ? 'bg-[#25963f] text-white shadow-md'
              : 'text-green-200 hover:text-white hover:bg-white/10'
              }`}
          >
            <item.icon className="w-4 h-4 shrink-0" />
            {item.label}
          </button>
        ))}
      </nav>

      {/* User */}
      <div className="px-3 py-4 border-t border-white/10">
        <div className="bg-white/10 rounded-lg px-3 py-2.5 flex items-center gap-2.5 mb-3">
          <div className="w-7 h-7 bg-[#25963f] rounded-full flex items-center justify-center font-bold text-xs shrink-0">
            {(leaderName || 'L')[0].toUpperCase()}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-white truncate">{leaderName || 'Leader'}</p>
            <p className="text-[10px] text-green-300">Corporator</p>
          </div>
        </div>
        <button onClick={onLogout} className="flex items-center gap-2 text-green-300 hover:text-white transition-colors text-xs px-1">
          <LogOut className="w-3.5 h-3.5" />
          Log Out
        </button>
      </div>
    </div>
  );
}
