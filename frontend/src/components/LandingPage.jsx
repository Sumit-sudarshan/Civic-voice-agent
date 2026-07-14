import React from 'react';
import { Home, Facebook, Twitter, Instagram, MessageSquareText } from 'lucide-react';

export default function LandingPage({ onFileComplaint, onLogin, onSignup }) {
  return (
    <div className="min-h-full font-sans flex flex-col bg-[#ebf5fb]">

      {/* White logo header */}
      <div className="bg-white px-4 sm:px-8 py-2 flex justify-between items-center border-b border-gray-100 shadow-sm">
        <div className="flex items-center gap-4">
          <div className="h-11 w-11 rounded-lg bg-[#0e75c6] flex items-center justify-center shrink-0">
            <MessageSquareText className="w-6 h-6 text-white" />
          </div>
          <div className="flex flex-col leading-tight">
            <span className="text-xl sm:text-2xl font-bold text-gray-900">Citizen's Portal</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={onSignup}
            className="bg-white text-[#0e75c6] text-sm font-semibold px-5 py-2 rounded border-2 border-[#0e75c6] hover:bg-[#eaf4ff] transition-colors"
          >
            Sign Up
          </button>
          <button
            onClick={onLogin}
            className="bg-[#0e75c6] text-white text-sm font-semibold px-5 py-2 rounded hover:bg-[#054483] transition-colors"
          >
            Login
          </button>
        </div>
      </div>

      {/* Dark blue nav bar */}
      <div className="bg-[#0e75c6] text-white px-4 sm:px-8 flex items-center gap-1 sm:gap-6 text-sm font-semibold shadow-md">
        <button className="py-3 px-2 hover:bg-[#1f93ff] transition-colors"><Home className="w-5 h-5"/></button>
        <button className="py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden sm:block">Track your Complaint</button>
        <button className="py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden md:block">Report & Check</button>
        <button className="py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden lg:block">Learning Corner</button>
        <button className="py-3 px-2 hover:bg-[#1f93ff] transition-colors hidden sm:block">Contact Us</button>
      </div>

      {/* Main body */}
      <div className="flex-1 bg-[#ebf5fb] px-4 py-10 sm:px-12">
        <div className="max-w-5xl mx-auto rounded-2xl bg-gradient-to-br from-[#1ea2fb] to-[#1176d6] shadow-xl overflow-hidden">
          <div className="px-8 py-10 sm:px-14 sm:py-12 text-white">
            <h2 className="text-2xl sm:text-3xl font-bold text-center mb-7 tracking-wide">
              Welcome to Citizen's Portal
            </h2>
            <div className="space-y-5 text-[15px] leading-relaxed text-blue-50 max-w-4xl mx-auto text-justify">
              <p>
                Citizen's Portal is an AI-powered platform that makes it easy to report issues and share ideas for improving your community. Simply describe what you've noticed, and our system takes care of the rest.
              </p>
              <p>
                Every submission is automatically analysed by our AI pipeline and routed to the right team for review, so concerns are addressed quickly and nothing falls through the cracks. You can track the status of your submissions at any time.
              </p>
            </div>
            <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-5">
              <button
                type="button"
                className="w-full sm:w-auto bg-[#054483] text-white border-2 border-white/80 rounded font-semibold px-8 py-2.5 hover:bg-[#03315e] transition-colors shadow"
              >
                Learn about Citizen's Portal
              </button>
              <button
                type="button"
                onClick={onLogin}
                className="w-full sm:w-auto bg-[#054483] text-white border-2 border-white/80 rounded font-semibold px-8 py-2.5 hover:bg-[#03315e] transition-colors shadow"
              >
                File a complaint
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
      </div>
    </div>
  );
}
