import React from 'react';
import { Home, ShieldCheck } from 'lucide-react';

// Leader-portal counterpart to LandingPage.jsx (citizen side). Same layout —
// logo header, nav bar, gradient welcome card, footer — mirrored in the
// leader's existing green theme (LeaderLogin.jsx / LeaderSignupPage.jsx)
// instead of the citizen blue. This is a pure entry/marketing screen: it
// calls no API itself, only routes to LeaderLogin/LeaderSignupPage, which
// already wire to POST /auth/login and POST /auth/leader/signup.
export default function LeaderLandingPage({ onLogin, onSignup, onGoToCitizenPortal }) {
  return (
    <div className="min-h-full font-sans flex flex-col bg-[#eef6ee]">

      {/* White logo header */}
      <div className="bg-white px-4 sm:px-8 py-2 flex justify-between items-center border-b border-gray-100 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="h-11 w-11 rounded-lg bg-[#1c7a3c] flex items-center justify-center shrink-0">
            <ShieldCheck className="w-6 h-6 text-white" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-xl sm:text-2xl font-bold text-gray-900">Leader's Portal</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onSignup}
            className="bg-white text-[#1c7a3c] text-sm font-semibold px-5 py-2 rounded border-2 border-[#1c7a3c] hover:bg-[#eaf7ec] transition-colors"
          >
            Register
          </button>
          <button
            onClick={onLogin}
            className="bg-[#1c7a3c] text-white text-sm font-semibold px-5 py-2 rounded hover:bg-[#155c2d] transition-colors"
          >
            Login
          </button>
        </div>
      </div>

      {/* Dark green nav bar */}
      <div className="bg-[#1c7a3c] text-white px-4 sm:px-8 flex items-center gap-1 sm:gap-6 text-sm font-semibold shadow-md">
        <button className="py-3 px-2 hover:bg-[#25963f] transition-colors"><Home className="w-5 h-5"/></button>
        <button className="py-3 px-2 hover:bg-[#25963f] transition-colors hidden sm:block">Your Ward Dashboard</button>
        <button className="py-3 px-2 hover:bg-[#25963f] transition-colors hidden md:block">Complaint Categories</button>
        <button className="py-3 px-2 hover:bg-[#25963f] transition-colors hidden lg:block">Resources</button>
        <button className="py-3 px-2 hover:bg-[#25963f] transition-colors hidden sm:block">Contact Support</button>
      </div>

      {/* Main body */}
      <div className="flex-1 bg-[#eef6ee] px-4 py-10 sm:px-12">
        <div className="max-w-5xl mx-auto rounded-2xl bg-gradient-to-br from-[#2f9e56] to-[#155c2d] shadow-xl overflow-hidden">
          <div className="px-8 py-10 sm:px-14 sm:py-12 text-white">
            <h2 className="text-2xl sm:text-3xl font-bold text-center mb-7 tracking-wide">
              Welcome to Leader's Portal
            </h2>
            <div className="space-y-5 text-[15px] leading-relaxed text-green-50 max-w-4xl mx-auto text-justify">
              <p>
                Leader's Portal gives corporators and ward representatives a single, categorized view of every
                complaint and suggestion raised in their jurisdiction — automatically classified, prioritized by
                urgency, and deduplicated by our AI pipeline before it ever reaches you.
              </p>
              <p>
                Sign in to see submissions filed for your city and pincode, track and update their status, and
                reveal a citizen's contact details when you need to follow up directly — every reveal is logged.
              </p>
            </div>
            <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-5">
              <button
                type="button"
                onClick={onSignup}
                className="w-full sm:w-auto bg-[#0f3d1f] text-white border-2 border-white/80 rounded font-semibold px-8 py-2.5 hover:bg-[#0a2c16] transition-colors shadow"
              >
                Register as a Leader
              </button>
              <button
                type="button"
                onClick={onLogin}
                className="w-full sm:w-auto bg-[#0f3d1f] text-white border-2 border-white/80 rounded font-semibold px-8 py-2.5 hover:bg-[#0a2c16] transition-colors shadow"
              >
                Login to Dashboard
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="bg-white border-t border-gray-200 text-xs text-gray-500 px-8 py-3 flex flex-wrap gap-4 justify-center">
        <span className="cursor-pointer hover:underline">Feedback</span>
        <span>|</span>
        <span className="cursor-pointer hover:underline">FAQ</span>
        <span>|</span>
        <span className="cursor-pointer hover:underline">Contact Us</span>
        <span>|</span>
        <span className="cursor-pointer hover:underline">Website Policies</span>
        <span>|</span>
        <span className="cursor-pointer hover:underline">Privacy Policy</span>
        <span>|</span>
        <span className="cursor-pointer hover:underline">Disclaimer</span>
        <span>|</span>
        <span className="cursor-pointer hover:underline font-semibold text-[#1c7a3c]" onClick={onGoToCitizenPortal}>Citizen Login</span>
      </div>
    </div>
  );
}
