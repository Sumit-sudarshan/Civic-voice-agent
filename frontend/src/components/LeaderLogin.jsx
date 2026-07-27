import React, { useState } from 'react';
import { Home, ShieldCheck, AlertTriangle } from 'lucide-react';
import { login } from '../api/auth';

export default function LeaderLogin({ onLoginSuccess, onSignup, onGoToCitizenLogin }) {
  const [email, setEmail]       = useState('');
  const [password, setPassword] = useState('');
  const [error, setError]       = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const user = await login({ email, password });
      if (user.role !== 'leader') {
        setError('This account is not registered as a leader. Use the citizen login instead.');
        return;
      }
      onLoginSuccess(user);
    } catch (err) {
      setError(err.message || 'Login failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-full flex flex-col font-sans bg-[#eef6ee]">

      {/* Logo header */}
      <div className="bg-white px-4 sm:px-8 py-2 flex justify-between items-center border-b border-gray-200 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="h-9 w-9 rounded-lg bg-[#1c7a3c] flex items-center justify-center shrink-0">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-lg sm:text-xl font-bold text-black">Leader's Portal</span>
          </div>
        </div>
      </div>

      {/* Nav — brand mark only, not a navigation control; only the buttons
          below and the "Citizen? Login here instead" link navigate anywhere. */}
      <div className="bg-[#1c7a3c] text-white px-4 sm:px-8 flex items-center gap-6 text-sm font-semibold shadow-md">
        <span className="py-3 px-2"><Home className="w-5 h-5"/></span>
        <button className="py-3 px-2 hover:bg-[#25963f] transition-colors hidden sm:block text-white">Your Ward Dashboard</button>
        <button className="py-3 px-2 hover:bg-[#25963f] transition-colors hidden sm:block text-white">Contact Support</button>
      </div>

      {/* Login card */}
      <div className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="bg-white rounded-xl shadow-md w-full max-w-lg px-10 py-8">
          <div className="flex items-center justify-center mb-5 gap-3">
            <div className="flex-1 h-px bg-[#1c7a3c]" />
            <h2 className="text-lg font-bold text-[#1c7a3c] tracking-widest whitespace-nowrap">LEADER LOGIN</h2>
            <div className="flex-1 h-px bg-[#1c7a3c]" />
          </div>

          <p className="text-xs text-gray-500 text-center mb-4">
            For corporators and ward representatives to view and manage complaints in their jurisdiction.
          </p>

          <div className="text-right mb-4">
            <button type="button" onClick={onSignup} className="text-blue-600 text-sm hover:underline font-medium">New Leader? Register Here</button>
          </div>
          <hr className="mb-5" />

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex items-center gap-3">
              <label className="text-sm font-bold text-black w-28 shrink-0">EMAIL: <span className="text-red-500">*</span></label>
              <input
                required type="email" value={email}
                onChange={e => { setEmail(e.target.value); setError(''); }}
                placeholder="you@example.com"
                className="flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black focus:outline-none focus:ring-1 focus:ring-green-400"
              />
            </div>

            <div className="flex items-center gap-3">
              <label className="text-sm font-bold text-black w-28 shrink-0">PASSWORD: <span className="text-red-500">*</span></label>
              <input
                required type="password" value={password}
                onChange={e => { setPassword(e.target.value); setError(''); }}
                placeholder="Your password"
                className="flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black focus:outline-none focus:ring-1 focus:ring-green-400"
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
                className="bg-[#1c7a3c] text-white px-8 py-2 rounded font-semibold hover:bg-[#155c2d] transition-colors text-sm disabled:opacity-50">
                {submitting ? 'Logging in…' : 'Login'}
              </button>
            </div>
          </form>

          <div className="mt-5 flex justify-between items-center">
            <button className="text-blue-600 text-sm font-bold hover:underline">Forgot Password</button>
            {onGoToCitizenLogin && (
              <button type="button" onClick={onGoToCitizenLogin} className="text-gray-500 text-xs hover:underline">
                Citizen? Login here instead
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
