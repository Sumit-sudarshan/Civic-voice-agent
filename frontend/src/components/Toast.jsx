import React, { useEffect, useState } from 'react';
import { CheckCircle2, XCircle, AlertCircle } from 'lucide-react';

/**
 * Self-dismissing toast notification.
 * 
 * Props:
 *   message  — text to show
 *   type     — 'success' | 'error' | 'info'
 *   onClose  — called when the toast dismisses itself (or user clicks ×)
 *   duration — ms before auto-dismiss (default 3000)
 */
export default function Toast({ message, type = 'success', onClose, duration = 3000 }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Fade in
    const showTimer = setTimeout(() => setVisible(true), 10);
    // Auto-dismiss
    const hideTimer = setTimeout(() => {
      setVisible(false);
      setTimeout(onClose, 300); // wait for fade-out transition
    }, duration);
    return () => { clearTimeout(showTimer); clearTimeout(hideTimer); };
  }, [duration, onClose]);

  const styles = {
    success: 'bg-green-50 border-green-200 text-green-800',
    error:   'bg-red-50 border-red-200 text-red-800',
    info:    'bg-blue-50 border-blue-200 text-blue-800',
  };

  const Icon = type === 'success' ? CheckCircle2 : type === 'error' ? XCircle : AlertCircle;

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl border shadow-lg text-sm font-medium
        transition-all duration-300 ease-out
        ${styles[type] || styles.info}
        ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}
    >
      <Icon className="w-4 h-4 flex-shrink-0" />
      <span>{message}</span>
      <button
        onClick={() => { setVisible(false); setTimeout(onClose, 300); }}
        className="ml-2 text-current opacity-50 hover:opacity-100 transition-opacity"
      >
        ×
      </button>
    </div>
  );
}
