import React, { useState } from 'react';
import { Home, MessageSquareText, CheckCircle2 } from 'lucide-react';

const initialForm = {
  firstName: '', lastName: '', email: '', phone: '',
  loginId: '', password: '', confirmPassword: '',
};

export default function SignupPage({ onBack, onGoToLogin }) {
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const handleChange = (e) => setForm((p) => ({ ...p, [e.target.name]: e.target.value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    if (form.password !== form.confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    if (form.password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    // No backend for signup — this is a simulated account creation. The
    // demo login (CitizenLogin.jsx) only ever accepts "CivicAgent" regardless
    // of what's entered here.
    setDone(true);
  };

  const inputCls = "flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black focus:outline-none focus:ring-1 focus:ring-blue-400";
  const labelCls = "text-sm font-bold text-black w-36 shrink-0";

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
        <button onClick={onBack} className="py-3 px-2 hover:bg-[#1f93ff] transition-colors"><Home className="w-5 h-5" /></button>
        <button className="py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden sm:block text-white">Track your Complaint</button>
        <button className="py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden sm:block text-white">Contact Us</button>
      </div>

      {/* Signup card */}
      <div className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="bg-white rounded-xl shadow-md w-full max-w-lg px-10 py-8">
          {done ? (
            <div className="text-center py-4">
              <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto mb-3" />
              <p className="font-bold text-black text-sm mb-1">Account Created</p>
              <p className="text-xs text-gray-600 mb-5">
                Welcome, <strong>{form.firstName} {form.lastName}</strong>. You can now log in with your Login ID.
              </p>
              <button
                onClick={onGoToLogin}
                className="bg-[#0e75c6] text-white px-6 py-2 rounded font-semibold text-sm hover:bg-[#054483] transition-colors"
              >
                Go to Login
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-center mb-5 gap-3">
                <div className="flex-1 h-px bg-green-600" />
                <h2 className="text-lg font-bold text-green-700 tracking-widest whitespace-nowrap">CITIZEN SIGN UP</h2>
                <div className="flex-1 h-px bg-green-600" />
              </div>

              <div className="text-right mb-4">
                <button type="button" onClick={onGoToLogin} className="text-blue-600 text-sm hover:underline font-medium">
                  Already have an account? Log in
                </button>
              </div>
              <hr className="mb-5" />

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="flex items-center gap-3">
                  <label className={labelCls}>FIRST NAME: <span className="text-red-500">*</span></label>
                  <input required name="firstName" value={form.firstName} onChange={handleChange} placeholder="First Name" className={inputCls} />
                </div>

                <div className="flex items-center gap-3">
                  <label className={labelCls}>LAST NAME: <span className="text-red-500">*</span></label>
                  <input required name="lastName" value={form.lastName} onChange={handleChange} placeholder="Last Name" className={inputCls} />
                </div>

                <div className="flex items-center gap-3">
                  <label className={labelCls}>EMAIL: <span className="text-red-500">*</span></label>
                  <input required type="email" name="email" value={form.email} onChange={handleChange} placeholder="you@example.com" className={inputCls} />
                </div>

                <div className="flex items-center gap-3">
                  <label className={labelCls}>MOBILE NO: <span className="text-red-500">*</span></label>
                  <input required type="tel" name="phone" value={form.phone} onChange={handleChange} placeholder="Mobile No." className={inputCls} />
                </div>

                <div className="flex items-center gap-3">
                  <label className={labelCls}>LOGIN ID: <span className="text-red-500">*</span></label>
                  <input required name="loginId" value={form.loginId} onChange={handleChange} placeholder="Choose a Login ID" className={inputCls} />
                </div>

                <div className="flex items-center gap-3">
                  <label className={labelCls}>PASSWORD: <span className="text-red-500">*</span></label>
                  <input required type="password" name="password" value={form.password} onChange={handleChange} placeholder="Create Password" className={`${inputCls} bg-gray-100`} />
                </div>

                <div className="flex items-center gap-3">
                  <label className={labelCls}>RE-ENTER: <span className="text-red-500">*</span></label>
                  <input required type="password" name="confirmPassword" value={form.confirmPassword} onChange={handleChange} placeholder="Re-enter Password" className={`${inputCls} bg-gray-100`} />
                </div>

                {error && <p className="text-red-500 text-xs text-center">{error}</p>}

                <div className="flex items-center justify-center pt-2">
                  <button type="submit" className="bg-green-600 text-white px-8 py-2 rounded font-semibold hover:bg-green-700 transition-colors text-sm">
                    Submit
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
