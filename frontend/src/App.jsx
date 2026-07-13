import React, { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import LandingPage from './components/LandingPage';
import CitizenDashboard from './components/CitizenDashboard';
import CitizenLogin from './components/CitizenLogin';
import SignupPage from './pages/SignupPage';
import Home from './pages/Home';
import Suggestions from './pages/Suggestions';
import Statistics from './pages/Statistics';
import Archive from './pages/Archive';
import Settings from './pages/Settings';
import EvalConsole from './pages/EvalConsole';

const SESSION_KEY = 'civic_citizen_session';

function App() {
  const [currentPath, setCurrentPath] = useState('home');
  const [isDashboard, setIsDashboard] = useState(false);
  const [view, setView] = useState(() => {
    const savedUser = localStorage.getItem(SESSION_KEY);
    return savedUser ? 'citizen-dashboard' : 'landing';
  }); // 'landing', 'login', 'citizen-dashboard', 'form'
  const [citizenUser, setCitizenUser] = useState(() => localStorage.getItem(SESSION_KEY) || '');

  useEffect(() => {
    // Simple native routing to split the app into two entry points
    if (window.location.pathname.startsWith('/dashboard')) {
      setIsDashboard(true);

      // Basic path parsing for dashboard sub-routes (e.g. /dashboard/complaints)
      const subRoute = window.location.pathname.split('/')[2];
      if (subRoute) {
        setCurrentPath(subRoute);
      }
    } else {
      setIsDashboard(false);
    }
  }, []);

  // Internal engineering-only route — deliberately not reachable from any nav
  // link in the citizen or leader UI, only by knowing the exact URL. Kept
  // after all hooks above so hook call order stays unconditional per render.
  if (window.location.pathname.startsWith('/internal-eval')) {
    return <EvalConsole />;
  }

  // Update URL without full reload when navigating within dashboard
  const handleNavigate = (path) => {
    setCurrentPath(path);
    window.history.pushState({}, '', `/dashboard/${path === 'home' ? '' : path}`);
  };

  const renderPage = () => {
    switch(currentPath) {
      case 'home': return <Home />;
      case 'suggestions': return <Suggestions />;
      case 'statistics': return <Statistics />;
      case 'archive': return <Archive />;
      case 'settings': return <Settings />;
      default: return <Home />;
    }
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[#fafafa] text-black">
      <div className="flex-1 flex overflow-hidden relative w-full">
        {isDashboard ? (
          <>
            <Sidebar active={currentPath} setActive={handleNavigate} />
            <main className="flex-1 overflow-y-auto relative z-10 w-full bg-[#fafafa]">
              {renderPage()}
            </main>
          </>
        ) : (
          <div className="flex-1 overflow-y-auto w-full">
            {(() => {
              switch (view) {
                case 'login':
                  return <CitizenLogin onLoginSuccess={(id) => { localStorage.setItem(SESSION_KEY, id); setCitizenUser(id); setView('citizen-dashboard'); }} onBack={() => setView('landing')} onSignup={() => setView('signup')} />;
                case 'signup':
                  return <SignupPage onBack={() => setView('landing')} onGoToLogin={() => setView('login')} />;
                case 'citizen-dashboard':
                  return <CitizenDashboard user={citizenUser} onLogout={() => { localStorage.removeItem(SESSION_KEY); setCitizenUser(''); setView('landing'); }} />;
                case 'landing':
                default:
                  return <LandingPage onLogin={() => setView('login')} onFileComplaint={() => setView('login')} onSignup={() => setView('signup')} />;
              }
            })()}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
