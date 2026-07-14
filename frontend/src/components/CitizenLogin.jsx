import React, { useState } from 'react';
import { Home, MessageSquareText } from 'lucide-react';

const CAPTCHA_TEXT = 'e2t2Up';

export default function CitizenLogin({ onLoginSuccess, onBack, onSignup }) {
  const [loginId, setLoginId]   = useState('');
  const [mobile, setMobile]     = useState('');
  const [otp, setOtp]           = useState('');
  const [captcha, setCaptcha]   = useState('');
  const [error, setError]       = useState('');

  const handleClear = () => {
    setLoginId(''); setMobile(''); setOtp(''); setCaptcha(''); setError('');
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (loginId === 'CivicAgent') {
      onLoginSuccess(loginId);
    } else {
      setError('Invalid Login ID. Use "CivicAgent" for demo access.');
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
            <div className="flex-1 h-px bg-green-600" />
            <h2 className="text-lg font-bold text-green-700 tracking-widest whitespace-nowrap">CITIZEN LOGIN</h2>
            <div className="flex-1 h-px bg-green-600" />
          </div>

          <div className="text-right mb-4">
            <button type="button" onClick={onSignup} className="text-blue-600 text-sm hover:underline font-medium">Click Here for New User</button>
          </div>
          <hr className="mb-5" />

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Login ID */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-bold text-black w-36 shrink-0">LOGIN ID: <span className="text-red-500">*</span></label>
              <input
                type="text" value={loginId}
                onChange={e => { setLoginId(e.target.value); setError(''); }}
                placeholder="Your Login Id"
                className="flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>

            <div className="flex items-center gap-3">
              <div className="w-36 shrink-0 flex flex-col">
                <label className="text-sm font-bold text-black">MOBILE NO: <span className="text-red-500">*</span></label>
              </div>
              <div className="flex flex-1 border border-gray-300 rounded-full overflow-hidden focus-within:ring-1 focus-within:ring-blue-400">
                <input
                  type="tel" value={mobile}
                  onChange={e => setMobile(e.target.value)}
                  placeholder="Mobile No."
                  className="flex-1 px-4 py-1.5 text-sm text-black bg-white focus:outline-none"
                />
                <button type="button" className="bg-blue-600 text-white text-xs font-semibold px-4 py-1.5 hover:bg-blue-700 whitespace-nowrap">Get OTP</button>
              </div>
            </div>

            {/* OTP */}
            <div className="flex items-center gap-3">
              <label className="text-sm font-bold text-black w-36 shrink-0">OTP: <span className="text-red-500">*</span></label>
              <input
                type="text" value={otp}
                onChange={e => setOtp(e.target.value)}
                placeholder="Your OTP Number"
                className="flex-1 border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black bg-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-400"
              />
            </div>

            {/* Captcha */}
            <div className="flex items-start gap-3 ml-[156px]">
              <div className="flex flex-col gap-2 flex-1">
                <div className="flex items-center gap-3">
                  {/* Captcha image mock */}
                  <div className="border border-gray-300 bg-gray-100 px-3 py-1 font-mono text-base text-black tracking-widest select-none rounded" style={{letterSpacing:'4px', fontFamily:'monospace', background:'repeating-linear-gradient(45deg,#ddd,#ddd 2px,#f5f5f5 2px,#f5f5f5 8px)'}}>
                    {CAPTCHA_TEXT}
                  </div>
                  <button type="button" className="text-blue-500 text-lg" title="Refresh captcha">↻</button>
                </div>
                <input
                  type="text" value={captcha}
                  onChange={e => setCaptcha(e.target.value)}
                  placeholder="Enter Captcha"
                  className="border border-gray-300 rounded-full px-4 py-1.5 text-sm text-black bg-gray-100 focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
            </div>

            {error && <p className="text-red-500 text-xs text-center">{error}</p>}

            <div className="flex items-center justify-center gap-4 pt-2">
              <button type="button" onClick={handleClear}
                className="bg-red-500 text-white px-7 py-2 rounded font-semibold hover:bg-red-600 transition-colors text-sm">Clear</button>
              <button type="submit"
                className="bg-green-600 text-white px-7 py-2 rounded font-semibold hover:bg-green-700 transition-colors text-sm">Submit</button>
            </div>
          </form>

          <div className="mt-5">
            <button className="text-blue-600 text-sm font-bold hover:underline">Forgot Login Id</button>
          </div>
        </div>
      </div>
    </div>
  );
}
