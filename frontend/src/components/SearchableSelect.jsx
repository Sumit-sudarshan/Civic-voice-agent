import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, X } from 'lucide-react';

// Small, dependency-free searchable combobox — no such library exists in
// this project's package.json, and pulling one in for a single dropdown
// wasn't worth it. Type to filter by label (case-insensitive substring);
// results are always shown alphabetically regardless of the order `options`
// arrives in, so a caller-side sort isn't required for correctness.
export default function SearchableSelect({
  options, value, onChange, placeholder = 'Search…',
  inputClassName = '', wrapperClassName = '', disabled = false,
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  const selected = options.find((o) => o.value === value) || null;

  // Keep the visible text in sync with an externally-changed selection
  // (e.g. the leaders list is refetched and the previous pick is gone).
  useEffect(() => {
    if (!open) setQuery(selected ? selected.label : '');
  }, [selected, open]);

  useEffect(() => {
    const onClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
        setQuery(selected ? selected.label : '');
      }
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, [selected]);

  const filtered = [...options]
    .filter((o) => o.label.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }));

  const handleSelect = (opt) => {
    onChange(opt.value);
    setQuery(opt.label);
    setOpen(false);
  };

  const handleClear = (e) => {
    e.stopPropagation();
    onChange('');
    setQuery('');
    setOpen(true);
  };

  return (
    <div ref={containerRef} className={`relative ${wrapperClassName}`}>
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (value) onChange('');
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') { setOpen(false); e.currentTarget.blur(); }
            if (e.key === 'Enter' && filtered.length === 1) { e.preventDefault(); handleSelect(filtered[0]); }
          }}
          placeholder={placeholder}
          disabled={disabled}
          className={inputClassName}
        />
        {selected ? (
          <button
            type="button"
            onClick={handleClear}
            tabIndex={-1}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            <X className="w-3 h-3" />
          </button>
        ) : (
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-400 pointer-events-none" />
        )}
      </div>
      {open && !disabled && (
        <div className="absolute z-50 mt-1 w-full max-h-48 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg">
          {filtered.length === 0 ? (
            <p className="px-3 py-2 text-xs text-gray-400">No matches</p>
          ) : (
            filtered.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => handleSelect(o)}
                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-blue-50 transition-colors ${
                  o.value === value ? 'bg-blue-50 font-semibold text-[#0e75c6]' : 'text-black'
                }`}
              >
                {o.label}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
