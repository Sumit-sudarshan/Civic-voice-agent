import React, { useState } from 'react';
import { Home, ShieldCheck, CheckCircle2 } from 'lucide-react';
import { leaderSignup } from '../api/auth';

const initialForm = {
  name: '', email: '', phone: '', city: '', pincode: '',
  password: '', confirmPassword: '',
};

export default function LeaderSignupPage({ onGoToLogin }) {
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleChange = (e) => setForm((p) => ({ ...p, [e.target.name]: e.target.value }));

  const handleSubmit = async (e) => {
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

    setSubmitting(true);
    try {
      await leaderSignup({
        name: form.name, phone: form.phone, email: form.email,
        password: form.password, city: form.city, pincode: form.pincode,
      });
      setDone(true);
    } catch (err) {
      setError(err.message || 'Registration failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls = "flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black focus:outline-none focus:ring-1 focus:ring-green-400";
  const labelCls = "text-sm font-bold text-black w-36 shrink-0";

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
          below and the "Already registered? Log in" link navigate anywhere. */}
      <div className="bg-[#1c7a3c] text-white px-4 sm:px-8 flex items-center gap-6 text-sm font-semibold shadow-md">
        <span className="py-3 px-2"><Home className="w-5 h-5" /></span>
        <button className="py-3 px-2 hover:bg-[#25963f] transition-colors hidden sm:block text-white">Your Ward Dashboard</button>
        <button className="py-3 px-2 hover:bg-[#25963f] transition-colors hidden sm:block text-white">Contact Support</button>
      </div>

      {/* Signup card */}
      <div className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="bg-white rounded-xl shadow-md w-full max-w-lg px-10 py-8">
          {done ? (
            <div className="text-center py-4">
              <CheckCircle2 className="w-12 h-12 text-green-500 mx-auto mb-3" />
              <p className="font-bold text-black text-sm mb-1">Registration Submitted</p>
              <p className="text-xs text-gray-600 mb-5">
                Welcome, <strong>{form.name}</strong>. Check your email to confirm your account, then log in to
                view complaints raised in your jurisdiction ({form.city}, {form.pincode}).
              </p>
              <button
                onClick={onGoToLogin}
                className="bg-[#1c7a3c] text-white px-6 py-2 rounded font-semibold text-sm hover:bg-[#155c2d] transition-colors"
              >
                Go to Login
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-center mb-5 gap-3">
                <div className="flex-1 h-px bg-[#1c7a3c]" />
                <h2 className="text-lg font-bold text-[#1c7a3c] tracking-widest whitespace-nowrap">LEADER REGISTRATION</h2>
                <div className="flex-1 h-px bg-[#1c7a3c]" />
              </div>

              <p className="text-xs text-gray-500 text-center mb-4">
                Register as a corporator or ward representative to receive complaints from citizens in your
                jurisdiction. No approval step — your account is active as soon as you confirm your email.
              </p>

              <div className="text-right mb-4">
                <button type="button" onClick={onGoToLogin} className="text-blue-600 text-sm hover:underline font-medium">
                  Already registered? Log in
                </button>
              </div>
              <hr className="mb-5" />

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="flex items-center gap-3">
                  <label className={labelCls}>NAME: <span className="text-red-500">*</span></label>
                  <input required name="name" value={form.name} onChange={handleChange} placeholder="Full Name" className={inputCls} />
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
                  <label className={labelCls}>CITY: <span className="text-red-500">*</span></label>
                  <input required name="city" value={form.city} onChange={handleChange} placeholder="City you represent" className={inputCls} />
                </div>

                <div className="flex items-center gap-3">
                  <label className={labelCls}>PINCODE: <span className="text-red-500">*</span></label>
                  <input required name="pincode" value={form.pincode} onChange={handleChange} placeholder="Jurisdiction pincode" className={inputCls} />
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
                  <button type="submit" disabled={submitting} className="bg-[#1c7a3c] text-white px-8 py-2 rounded font-semibold hover:bg-[#155c2d] transition-colors text-sm disabled:opacity-50">
                    {submitting ? 'Registering…' : 'Register'}
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
