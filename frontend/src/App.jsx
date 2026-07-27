import React, { useState, useEffect, lazy, Suspense } from 'react';
import { CheckCircle2 } from 'lucide-react';
import Sidebar from './components/Sidebar';
import LandingPage from './components/LandingPage';
import LeaderLandingPage from './components/LeaderLandingPage';
import CitizenDashboard from './components/CitizenDashboard';
import CitizenLogin from './components/CitizenLogin';
import LeaderLogin from './components/LeaderLogin';
import SignupPage from './pages/SignupPage';
import LeaderSignupPage from './pages/LeaderSignupPage';
import { getMe, logout as apiLogout } from './api/auth';

// Code-split the leader dashboard and the internal eval console out of the
// initial bundle. Everything below is reachable only after a leader logs in
// (or via the unlinked /internal-eval URL), while the bundle's single biggest
// dependency — recharts, pulled in by Statistics — was being shipped to every
// citizen who just wanted to file a complaint. Vite had warned about the
// >500 kB chunk on every build since the project started.
const Home = lazy(() => import('./pages/Home'));
const Suggestions = lazy(() => import('./pages/Suggestions'));
const Statistics = lazy(() => import('./pages/Statistics'));
const Archive = lazy(() => import('./pages/Archive'));
const Settings = lazy(() => import('./pages/Settings'));
const EvalConsole = lazy(() => import('./pages/EvalConsole'));

const PageFallback = () => (
  <div className="h-full flex items-center justify-center text-sm text-gray-500">Loading…</div>
);

// Supabase's email-confirmation link is verified entirely on Supabase's own
// server — it never touches our backend. Once confirmed, Supabase redirects
// the browser straight back to the app's root URL with the resulting session
// appended as a URL *fragment* (`#access_token=...&type=signup`), not a query
// string or a backend callback. Nothing previously read that fragment, so a
// leader confirming their email just silently landed on the citizen landing
// page with a live token sitting unused (and exposed) in the address bar.
//
// This only decodes the token to read `user_metadata.role` for routing —
// picking which portal's login screen to show — it is NOT treated as proof
// of identity; the user still has to log in with real credentials afterward.
function decodeSupabaseRole(accessToken) {
  try {
    let payload = accessToken.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    while (payload.length % 4) payload += '=';
    const claims = JSON.parse(atob(payload));
    return claims?.user_metadata?.role === 'leader' ? 'leader' : 'citizen';
  } catch {
    return 'citizen';
  }
}

function App() {
  const [currentPath, setCurrentPath] = useState('home');
  const [isDashboard, setIsDashboard] = useState(false);
  // Real session, restored on load from the httpOnly cookie via /auth/me —
  // there is no local pseudo-identity anymore (MVP_Design.md §5: session
  // lives server-side in the cookie, never localStorage).
  const [authLoading, setAuthLoading] = useState(true);
  const [user, setUser] = useState(null); // null = logged out; else {id,email,role,first_name,last_name,phone}
  const [citizenView, setCitizenView] = useState('landing'); // 'landing' | 'login' | 'signup'
  const [leaderView, setLeaderView] = useState('landing'); // 'landing' | 'login' | 'signup'
  const [confirmedRole, setConfirmedRole] = useState(null); // set when this load is a Supabase signup-confirmation redirect

  useEffect(() => {
    if (window.location.pathname.startsWith('/dashboard')) {
      setIsDashboard(true);
      const subRoute = window.location.pathname.split('/')[2];
      if (subRoute) setCurrentPath(subRoute);
    } else {
      setIsDashboard(false);
    }

    const hash = window.location.hash;
    if (hash.includes('access_token') && hash.includes('type=signup')) {
      const params = new URLSearchParams(hash.slice(1));
      const role = decodeSupabaseRole(params.get('access_token') || '');
      // The token is a live credential — strip it from the address bar/history
      // immediately rather than leaving it sitting there after we've read it.
      window.history.replaceState({}, '', window.location.pathname || '/');
      setConfirmedRole(role);
      if (role === 'leader') setLeaderView('login'); else setCitizenView('login');
    }

    getMe().then(setUser).catch(() => setUser(null)).finally(() => setAuthLoading(false));
  }, []);

  // Internal engineering-only route — deliberately not reachable from any nav
  // link in the citizen or leader UI, only by knowing the exact URL. Kept
  // after all hooks above so hook call order stays unconditional per render.
  if (window.location.pathname.startsWith('/internal-eval')) {
    return <Suspense fallback={<PageFallback />}><EvalConsole /></Suspense>;
  }

  // Just arrived here via a Supabase email-confirmation redirect — show a
  // clear confirmation instead of silently falling through to the citizen
  // landing page with an unused token in the address bar (see
  // decodeSupabaseRole's comment above for why that fragment exists at all).
  if (confirmedRole) {
    const isLeader = confirmedRole === 'leader';
    return (
      <div className={`h-screen flex items-center justify-center font-sans px-4 ${isLeader ? 'bg-[#eef6ee]' : 'bg-[#ebf5fb]'}`}>
        <div className="bg-white rounded-xl shadow-md w-full max-w-md px-8 py-10 text-center">
          <div className={`h-14 w-14 rounded-full mx-auto mb-4 flex items-center justify-center ${isLeader ? 'bg-[#1c7a3c]' : 'bg-[#0e75c6]'}`}>
            <CheckCircle2 className="w-8 h-8 text-white" />
          </div>
          <h2 className="text-lg font-bold text-black mb-2">Email confirmed</h2>
          <p className="text-sm text-gray-600 mb-6">
            Your {isLeader ? 'leader' : 'citizen'} account is now active. Please log in to continue.
          </p>
          <button
            onClick={() => {
              setConfirmedRole(null);
              if (isLeader) {
                setLeaderView('login');
                setIsDashboard(true);
                window.history.pushState({}, '', '/dashboard');
              } else {
                setCitizenView('login');
                setIsDashboard(false);
                window.history.pushState({}, '', '/');
              }
            }}
            className={`px-6 py-2 rounded font-semibold text-sm text-white transition-colors ${
              isLeader ? 'bg-[#1c7a3c] hover:bg-[#155c2d]' : 'bg-[#0e75c6] hover:bg-[#054483]'
            }`}
          >
            Go to {isLeader ? 'Leader' : 'Citizen'} Login
          </button>
        </div>
      </div>
    );
  }

  // Update URL without full reload when navigating within dashboard
  const handleNavigate = (path) => {
    setCurrentPath(path);
    window.history.pushState({}, '', `/dashboard/${path === 'home' ? '' : path}`);
  };

  const handleLogout = async () => {
    try { await apiLogout(); } catch { /* cookie may already be gone — clear local state regardless */ }
    setUser(null);
    setCitizenView('landing');
    setLeaderView('landing');
  };

  const renderPage = () => {
    switch (currentPath) {
      case 'home': return <Home leaderName={user?.leader?.name || user?.first_name || user?.name} />;
      case 'suggestions': return <Suggestions />;
      case 'statistics': return <Statistics />;
      case 'archive': return <Archive />;
      case 'settings': return <Settings />;
      default: return <Home />;
    }
  };

  if (authLoading) {
    return <div className="h-screen flex items-center justify-center bg-[#fafafa] text-sm text-gray-500">Loading…</div>;
  }

  const goToDashboard = () => {
    setIsDashboard(true);
    window.history.pushState({}, '', '/dashboard');
  };
  const goToCitizenHome = () => {
    setIsDashboard(false);
    window.history.pushState({}, '', '/');
  };

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[#fafafa] text-black">
      <div className="flex-1 flex overflow-hidden relative w-full">
        {isDashboard ? (
          user && user.role === 'leader' ? (
            <>
              <Sidebar
                active={currentPath}
                setActive={handleNavigate}
                leaderName={user.leader?.name || user.first_name || user.name}
                onLogout={handleLogout}
              />
              <main className="flex-1 overflow-y-auto relative z-10 w-full bg-[#fafafa]">
                <Suspense fallback={<PageFallback />}>{renderPage()}</Suspense>
              </main>
            </>
          ) : (
            <div className="flex-1 overflow-y-auto w-full">
              {(() => {
                switch (leaderView) {
                  case 'login':
                    return (
                      <LeaderLogin
                        onSignup={() => setLeaderView('signup')}
                        onGoToCitizenLogin={goToCitizenHome}
                        onLoginSuccess={(u) => setUser(u)}
                      />
                    );
                  case 'signup':
                    return (
                      <LeaderSignupPage
                        onGoToLogin={() => setLeaderView('login')}
                      />
                    );
                  case 'landing':
                  default:
                    return (
                      <LeaderLandingPage
                        onLogin={() => setLeaderView('login')}
                        onSignup={() => setLeaderView('signup')}
                        onGoToCitizenPortal={goToCitizenHome}
                      />
                    );
                }
              })()}
            </div>
          )
        ) : (
          <div className="flex-1 overflow-y-auto w-full">
            {user && user.role === 'citizen' ? (
              <CitizenDashboard user={user} onLogout={handleLogout} />
            ) : (
              (() => {
                switch (citizenView) {
                  case 'login':
                    return (
                      <CitizenLogin
                        onLoginSuccess={(u) => setUser(u)}
                        onBack={() => setCitizenView('landing')}
                        onSignup={() => setCitizenView('signup')}
                        onGoToLeaderLogin={goToDashboard}
                      />
                    );
                  case 'signup':
                    return <SignupPage onBack={() => setCitizenView('landing')} onGoToLogin={() => setCitizenView('login')} />;
                  case 'landing':
                  default:
                    return (
                      <LandingPage
                        onLogin={() => setCitizenView('login')}
                        onFileComplaint={() => setCitizenView('login')}
                        onSignup={() => setCitizenView('signup')}
                        onLeaderLogin={goToDashboard}
                      />
                    );
                }
              })()
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
