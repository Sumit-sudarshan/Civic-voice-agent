import React, { useState, useEffect } from 'react';
import { fetchCategories } from '../api/client';
import { Settings as SettingsIcon, Save } from 'lucide-react';

export default function Settings() {
  const [categories, setCategories] = useState([]);

  useEffect(() => {
    fetchCategories().then(setCategories).catch(console.error);
  }, []);

  return (
    <div className="px-6 py-5 max-w-4xl mx-auto">
      <div className="mb-5">
        <h1 className="text-xl font-bold text-black mb-0.5">Settings</h1>
        <p className="text-xs text-gray-500">Platform configuration and system preferences.</p>
      </div>

      <div className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 flex items-center gap-3">
          <div className="w-8 h-8 bg-[#eaf7ec] rounded-md flex items-center justify-center border border-green-100">
            <SettingsIcon className="w-4 h-4 text-[#1c7a3c]" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-black">Complaint Categories</h3>
            <p className="text-xs text-gray-500">Categories available in the citizen intake form.</p>
          </div>
        </div>
        
        <div className="p-4">
          <ul className="space-y-2 mb-4">
            {categories.map(c => (
              <li key={c} className="flex items-center justify-between px-3 py-2 bg-gray-50 border border-gray-100 rounded-md">
                <span className="text-xs font-medium capitalize text-black">{c}</span>
                <span className="text-[10px] text-gray-500 font-semibold bg-gray-200 px-2 py-0.5 rounded">Built-in</span>
              </li>
            ))}
          </ul>
          
          <div className="flex gap-2">
            <input 
              type="text" 
              placeholder="New Category Name (Phase 16)" 
              disabled
              className="flex-1 px-3 py-2 border border-gray-200 rounded-md bg-gray-50 text-gray-400 cursor-not-allowed text-xs focus:outline-none"
            />
            <button disabled className="px-4 py-2 bg-gray-100 text-gray-400 rounded-md font-medium cursor-not-allowed text-xs flex items-center gap-1.5 border border-gray-200">
              <Save className="w-3.5 h-3.5" /> Add
            </button>
          </div>
          <p className="text-[10px] text-gray-400 mt-2 text-right">Category editing requires Authentication (Phase 16)</p>
        </div>
      </div>
    </div>
  );
}
