import React, { useState } from 'react';
import { Home, MessageSquareText, AlertTriangle } from 'lucide-react';
import { login } from '../api/auth';

export default function CitizenLogin({ onLoginSuccess, onBack, onSignup, onGoToLeaderLogin }) {
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
      onLoginSuccess(user);
    } catch (err) {
      setError(err.message || 'Login failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-full flex flex-col font-sans bg-[#ebf5fb]">

      {/* Logo header */}
      <div className="bg-white px-4 sm:px-8 py-2 flex justify-between items-center border-b border-gray-200 shadow-sm">
        <div className="flex items-center gap-4 cursor-pointer" onClick={onBack}>
          <div className="h-9 w-9 rounded-lg bg-[#0e75c6] flex items-center justify-center shrink-0">
            <MessageSquareText className="w-5 h-5 text-white" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-lg sm:text-xl font-bold text-black">Citizen's Portal</span>
          </div>
        </div>
      </div>

      {/* Nav */}
      <div className="bg-[#0e75c6] text-white px-4 sm:px-8 flex items-center gap-6 text-sm font-semibold shadow-md">
        <button onClick={onBack} className="py-3 px-2 hover:bg-[#1f93ff] transition-colors"><Home className="w-5 h-5"/></button>
        <button className="py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden sm:block text-white">Track your Complaint</button>
        <button className="py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden sm:block text-white">Contact Us</button>
      </div>

      {/* Login card */}
      <div className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="bg-white rounded-xl shadow-md w-full max-w-lg px-10 py-8">
          {/* Title */}
          <div className="flex items-center justify-center mb-5 gap-3">
            <div className="flex-1 h-px bg-[#0e75c6]" />
            <h2 className="text-lg font-bold text-[#0e75c6] tracking-widest whitespace-nowrap">CITIZEN LOGIN</h2>
            <div className="flex-1 h-px bg-[#0e75c6]" />
          </div>

          <div className="text-right mb-4">
            <button type="button" onClick={onSignup} className="text-blue-600 text-sm hover:underline font-medium">Click Here for New User</button>
          </div>
          <hr className="mb-5" />

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex items-center gap-3">
              <label className="text-sm font-bold text-black w-28 shrink-0">EMAIL: <span className="text-red-500">*</span></label>
              <input
                required type="email" value={email}
                onChange={e => { setEmail(e.target.value); setError(''); }}
                placeholder="you@example.com"
                className="flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>

            <div className="flex items-center gap-3">
              <label className="text-sm font-bold text-black w-28 shrink-0">PASSWORD: <span className="text-red-500">*</span></label>
              <input
                required type="password" value={password}
                onChange={e => { setPassword(e.target.value); setError(''); }}
                placeholder="Your password"
                className="flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black focus:outline-none focus:ring-1 focus:ring-blue-400"
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
                className="bg-[#0e75c6] text-white px-8 py-2 rounded font-semibold hover:bg-[#054483] transition-colors text-sm disabled:opacity-50">
                {submitting ? 'Logging in…' : 'Login'}
              </button>
            </div>
          </form>

          <div className="mt-5 flex justify-between items-center">
            <button className="text-blue-600 text-sm font-bold hover:underline">Forgot Password</button>
            {onGoToLeaderLogin && (
              <button type="button" onClick={onGoToLeaderLogin} className="text-gray-500 text-xs hover:underline">
                Are you a leader? Login here
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
