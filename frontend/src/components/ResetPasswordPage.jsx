import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, MessageSquareText, ShieldCheck } from 'lucide-react';
import { resetPassword } from '../api/auth';

const THEME = {
  citizen: { bg: 'bg-[#ebf5fb]', accent: '#0e75c6', ring: 'focus:ring-blue-400', icon: MessageSquareText, portal: "Citizen's Portal" },
  leader: { bg: 'bg-[#eef6ee]', accent: '#1c7a3c', ring: 'focus:ring-green-400', icon: ShieldCheck, portal: "Leader's Portal" },
};

export default function ResetPasswordPage({ variant, accessToken, onDone }) {
  const t = THEME[variant] || THEME.citizen;
  const Icon = t.icon;
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    setSubmitting(true);
    try {
      await resetPassword({ accessToken, newPassword: password });
      setDone(true);
    } catch (err) {
      setError(err.message || 'Could not reset password. The link may have expired — request a new one.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={`h-screen flex flex-col font-sans ${t.bg}`}>
      <div className="bg-white px-4 sm:px-8 py-2 flex items-center gap-4 border-b border-gray-200 shadow-sm">
        <div className="h-9 w-9 rounded-lg flex items-center justify-center shrink-0" style={{ backgroundColor: t.accent }}>
          <Icon className="w-5 h-5 text-white" />
        </div>
        <span className="text-lg sm:text-xl font-bold text-black">{t.portal}</span>
      </div>

      <div className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="bg-white rounded-xl shadow-md w-full max-w-lg px-10 py-8">
          {done ? (
            <div className="text-center py-4">
              <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto mb-3" />
              <p className="font-bold text-black text-sm mb-1">Password updated</p>
              <p className="text-xs text-gray-600 mb-5">You can now log in with your new password.</p>
              <button
                onClick={onDone}
                className="text-white px-6 py-2 rounded font-semibold text-sm transition-colors"
                style={{ backgroundColor: t.accent }}
              >
                Go to Login
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-center mb-5 gap-3">
                <div className="flex-1 h-px" style={{ backgroundColor: t.accent }} />
                <h2 className="text-lg font-bold tracking-widest whitespace-nowrap" style={{ color: t.accent }}>SET NEW PASSWORD</h2>
                <div className="flex-1 h-px" style={{ backgroundColor: t.accent }} />
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="flex items-center gap-3">
                  <label className="text-sm font-bold text-black w-32 shrink-0">NEW PASSWORD: <span className="text-red-500">*</span></label>
                  <input
                    required type="password" value={password}
                    onChange={e => { setPassword(e.target.value); setError(''); }}
                    placeholder="Create a new password"
                    className={`flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black bg-gray-100 focus:outline-none focus:ring-1 ${t.ring}`}
                  />
                </div>
                <div className="flex items-center gap-3">
                  <label className="text-sm font-bold text-black w-32 shrink-0">RE-ENTER: <span className="text-red-500">*</span></label>
                  <input
                    required type="password" value={confirmPassword}
                    onChange={e => { setConfirmPassword(e.target.value); setError(''); }}
                    placeholder="Re-enter password"
                    className={`flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black bg-gray-100 focus:outline-none focus:ring-1 ${t.ring}`}
                  />
                </div>

                {error && (
                  <div className="flex items-start gap-2 p-2.5 rounded border bg-red-50 border-red-200">
                    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-red-500" />
                    <p className="text-xs text-red-700">{error}</p>
                  </div>
                )}

                <div className="flex items-center justify-center pt-2">
                  <button type="submit" disabled={submitting}
                    className="text-white px-8 py-2 rounded font-semibold text-sm transition-colors disabled:opacity-50"
                    style={{ backgroundColor: t.accent }}>
                    {submitting ? 'Updating…' : 'Update Password'}
                  </button>
                </div>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
