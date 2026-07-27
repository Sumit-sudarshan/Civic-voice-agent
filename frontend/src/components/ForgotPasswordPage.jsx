import React, { useState } from 'react';
import { AlertTriangle, CheckCircle2, MessageSquareText, ShieldCheck } from 'lucide-react';
import { forgotPassword } from '../api/auth';

// Shared by both portals (citizen + leader) rather than two near-duplicate
// files — unlike the signup forms (different fields per role), this form is
// identical either way; only the theme colors and heading differ.
const THEME = {
  citizen: { bg: 'bg-[#ebf5fb]', accent: '#0e75c6', accentHover: '#054483', ring: 'focus:ring-blue-400', icon: MessageSquareText, portal: "Citizen's Portal" },
  leader: { bg: 'bg-[#eef6ee]', accent: '#1c7a3c', accentHover: '#155c2d', ring: 'focus:ring-green-400', icon: ShieldCheck, portal: "Leader's Portal" },
};

export default function ForgotPasswordPage({ variant, onBack }) {
  const t = THEME[variant];
  const Icon = t.icon;
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await forgotPassword({ email });
      setDone(true);
    } catch (err) {
      setError(err.message || 'Something went wrong. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={`min-h-full flex flex-col font-sans ${t.bg}`}>
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
              <p className="font-bold text-black text-sm mb-1">Check your email</p>
              <p className="text-xs text-gray-600 mb-5">
                If an account with that email exists, a password reset link has been sent. Open it to set a new password.
              </p>
              <button
                onClick={onBack}
                className="text-white px-6 py-2 rounded font-semibold text-sm transition-colors"
                style={{ backgroundColor: t.accent }}
              >
                Back to Login
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-center mb-5 gap-3">
                <div className="flex-1 h-px" style={{ backgroundColor: t.accent }} />
                <h2 className="text-lg font-bold tracking-widest whitespace-nowrap" style={{ color: t.accent }}>RESET PASSWORD</h2>
                <div className="flex-1 h-px" style={{ backgroundColor: t.accent }} />
              </div>
              <p className="text-xs text-gray-500 text-center mb-5">
                Enter the email on your account and we'll send you a link to reset your password.
              </p>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="flex items-center gap-3">
                  <label className="text-sm font-bold text-black w-20 shrink-0">EMAIL: <span className="text-red-500">*</span></label>
                  <input
                    required type="email" value={email}
                    onChange={e => { setEmail(e.target.value); setError(''); }}
                    placeholder="you@example.com"
                    className={`flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black focus:outline-none focus:ring-1 ${t.ring}`}
                  />
                </div>

                {error && (
                  <div className="flex items-start gap-2 p-2.5 rounded border bg-red-50 border-red-200">
                    <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-red-500" />
                    <p className="text-xs text-red-700">{error}</p>
                  </div>
                )}

                <div className="flex items-center justify-center gap-4 pt-2">
                  <button type="button" onClick={onBack} className="text-gray-500 text-sm hover:underline">Back to Login</button>
                  <button type="submit" disabled={submitting}
                    className="text-white px-8 py-2 rounded font-semibold text-sm transition-colors disabled:opacity-50"
                    style={{ backgroundColor: t.accent }}>
                    {submitting ? 'Sending…' : 'Send Reset Link'}
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
