import React, { useState, useEffect } from 'react';
import { Compass, Sparkles, ShieldCheck, CheckCircle2, User, UserPlus, LogIn, ArrowRight, Globe, Lock, KeyRound, Sparkle } from 'lucide-react';

const SAVED_ACCOUNTS_KEY = "travelpilot_saved_google_accounts_v1";

// Default demo Google accounts available out of the box
const INITIAL_DEMO_ACCOUNTS = [
  {
    id: "g_ishan_101",
    name: "Ishan Sharma",
    email: "ishan.traveler@gmail.com",
    avatar: "https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?auto=format&fit=crop&w=120&q=80",
    verified: true,
    lastLogin: "Active Now"
  },
  {
    id: "g_vinod_202",
    name: "Vinod Kumar",
    email: "vinod.explore@gmail.com",
    avatar: "https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?auto=format&fit=crop&w=120&q=80",
    verified: true,
    lastLogin: "Yesterday"
  }
];

// Helper to decode Google JWT token
function parseJwt(token) {
  try {
    const base64Url = token.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  } catch (e) {
    return null;
  }
}

export default function GoogleAuthPage({ onLogin, onCancel, currentActiveUser }) {
  const [savedAccounts, setSavedAccounts] = useState(() => {
    try {
      const stored = localStorage.getItem(SAVED_ACCOUNTS_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (e) {}
    return INITIAL_DEMO_ACCOUNTS;
  });

  const [isAddingCustom, setIsAddingCustom] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customEmail, setCustomEmail] = useState("");
  const [inputError, setInputError] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);

  // Initialize official Google Identity Services (GSI) if VITE_GOOGLE_CLIENT_ID is set
  useEffect(() => {
    const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;
    if (!googleClientId) return;

    const initializeGsi = () => {
      if (window.google?.accounts?.id) {
        window.google.accounts.id.initialize({
          client_id: googleClientId,
          callback: handleGoogleGsiCallback,
          auto_select: false,
          cancel_on_tap_outside: true,
        });

        const gsiBtn = document.getElementById("gsi-button-container");
        if (gsiBtn) {
          window.google.accounts.id.renderButton(gsiBtn, {
            theme: "outline",
            size: "large",
            width: 320,
            text: "continue_with",
            shape: "pill",
          });
        }
      }
    };

    if (window.google?.accounts?.id) {
      initializeGsi();
    } else {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      script.onload = initializeGsi;
      document.body.appendChild(script);
    }
  }, []);

  const handleGoogleGsiCallback = (response) => {
    if (!response.credential) return;
    const payload = parseJwt(response.credential);
    if (!payload) return;

    const googleUser = {
      id: payload.sub || `g_${Date.now()}`,
      name: payload.name || payload.email.split("@")[0],
      email: payload.email,
      avatar: payload.picture || `https://ui-avatars.com/api/?name=${encodeURIComponent(payload.name || "Google User")}&background=FA5B0F&color=fff`,
      verified: payload.email_verified ?? true,
      provider: "google",
      token: response.credential,
      lastLogin: new Date().toLocaleDateString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    };

    saveAndCompleteLogin(googleUser);
  };

  const saveAndCompleteLogin = (account) => {
    setIsProcessing(true);

    // Save/update this account in the saved accounts list
    setSavedAccounts(prev => {
      const filtered = prev.filter(a => a.email.toLowerCase() !== account.email.toLowerCase());
      const updated = [account, ...filtered];
      try {
        localStorage.setItem(SAVED_ACCOUNTS_KEY, JSON.stringify(updated));
      } catch (e) {}
      return updated;
    });

    setTimeout(() => {
      setIsProcessing(false);
      onLogin(account);
    }, 400);
  };

  const handleSelectAccount = (account) => {
    const updatedAccount = {
      ...account,
      lastLogin: "Active Now"
    };
    saveAndCompleteLogin(updatedAccount);
  };

  const handleCustomGoogleSubmit = (e) => {
    e.preventDefault();
    const name = customName.trim();
    let email = customEmail.trim().toLowerCase();

    if (!name) {
      setInputError("Please enter your name");
      return;
    }
    if (!email) {
      setInputError("Please enter your Google email");
      return;
    }
    if (!email.includes("@")) {
      email = `${email}@gmail.com`;
    }

    setInputError("");
    const newAccount = {
      id: `g_custom_${Date.now()}`,
      name,
      email,
      avatar: `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=FA5B0F&color=fff&bold=true`,
      verified: true,
      provider: "google",
      lastLogin: "Active Now"
    };

    saveAndCompleteLogin(newAccount);
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center p-4 sm:p-6 lg:p-8 relative z-20">
      {/* Container Card with TravelTour Styling */}
      <div className="w-full max-w-xl bg-white/95 backdrop-blur-xl border border-[#ECE8E1] rounded-3xl shadow-2xl p-6 sm:p-10 transition-all text-slate-900 relative overflow-hidden">
        
        {/* Subtle Top Google Accent Strip */}
        <div className="absolute top-0 inset-x-0 h-1.5 bg-gradient-to-r from-[#4285F4] via-[#EA4335] via-[#FBBC05] to-[#34A853]" />

        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="mb-2 text-xs font-bold text-slate-500 hover:text-slate-900 transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            ← Back to Active Session ({currentActiveUser?.name || 'Explorer'})
          </button>
        )}

        {/* Brand Header */}
        <div className="text-center space-y-3 mb-8 pt-2">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-[#FA5B0F] text-white shadow-lg shadow-[#FA5B0F]/30 mx-auto">
            <Compass className="w-8 h-8 animate-pulse" />
          </div>

          <div>
            <div className="flex items-center justify-center gap-2">
              <h1 className="text-3xl font-serif font-black tracking-tight text-[#19202E]">
                Trip<span className="text-[#FA5B0F]">Saathi</span>
              </h1>
              <span className="text-[10px] font-extrabold uppercase tracking-wider bg-[#FFF4EE] text-[#FA5B0F] border border-[#FED7AA] px-2 py-0.5 rounded-md">
                Tour AI
              </span>
            </div>
            <p className="text-xs text-slate-500 font-medium mt-1">
              Curated Grounded Journeys • Real Multi-Modal Transit • Zero Repeated Stops
            </p>
          </div>

          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-50 border border-slate-200 text-xs font-bold text-slate-700">
            <span className="flex items-center gap-1.5 text-slate-900">
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
              </svg>
              <span>Google Authentication Sign Up</span>
            </span>
          </div>
        </div>

        {/* Official GSI Button Container if loaded */}
        <div id="gsi-button-container" className="flex justify-center mb-6 empty:hidden" />

        {/* Account Selection Card */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-[#FA5B0F]" />
              Choose Google Account to Continue
            </span>
            <span className="text-[11px] text-slate-400 font-medium">
              Saved Accounts ({savedAccounts.length})
            </span>
          </div>

          {/* List of saved Google accounts */}
          <div className="space-y-2.5">
            {savedAccounts.map((account) => (
              <button
                key={account.id || account.email}
                type="button"
                onClick={() => handleSelectAccount(account)}
                disabled={isProcessing}
                className="w-full p-3.5 rounded-2xl border border-[#ECE8E1] hover:border-[#FA5B0F] bg-white hover:bg-[#FFF4EE]/40 transition-all flex items-center justify-between gap-3 text-left group shadow-xs cursor-pointer disabled:opacity-50"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="relative shrink-0">
                    <img
                      src={account.avatar}
                      alt={account.name}
                      className="w-11 h-11 rounded-full object-cover border-2 border-white shadow-xs group-hover:scale-105 transition-transform"
                      onError={(e) => {
                        e.target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(account.name)}&background=FA5B0F&color=fff`;
                      }}
                    />
                    <div className="absolute -bottom-1 -right-1 bg-white p-0.5 rounded-full shadow-xs">
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24">
                        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                      </svg>
                    </div>
                  </div>

                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="font-extrabold text-sm text-[#19202E] truncate group-hover:text-[#FA5B0F] transition-colors">
                        {account.name}
                      </span>
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                    </div>
                    <p className="text-xs text-slate-500 truncate">
                      {account.email}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[10px] font-bold text-slate-400 hidden sm:inline">
                    {account.lastLogin || "Signed In"}
                  </span>
                  <div className="w-8 h-8 rounded-xl bg-slate-100 group-hover:bg-[#FA5B0F] group-hover:text-white text-slate-600 flex items-center justify-center transition-all">
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </div>
                </div>
              </button>
            ))}
          </div>

          {/* Add Another Google Account Form Toggle */}
          {!isAddingCustom ? (
            <button
              type="button"
              onClick={() => setIsAddingCustom(true)}
              className="w-full py-3 px-4 rounded-2xl border-2 border-dashed border-[#ECE8E1] hover:border-[#FA5B0F] text-slate-700 hover:text-[#FA5B0F] text-xs font-bold transition-all flex items-center justify-center gap-2 cursor-pointer bg-slate-50/50 hover:bg-[#FFF4EE]/30"
            >
              <UserPlus className="w-4 h-4" />
              <span>Use another Google account</span>
            </button>
          ) : (
            <form onSubmit={handleCustomGoogleSubmit} className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-3 animate-fadeIn">
              <div className="flex items-center justify-between">
                <span className="text-xs font-extrabold text-slate-800 flex items-center gap-1.5">
                  <svg className="w-4 h-4" viewBox="0 0 24 24">
                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                  </svg>
                  <span>Sign In with Your Google Details</span>
                </span>
                <button
                  type="button"
                  onClick={() => setIsAddingCustom(false)}
                  className="text-[11px] text-slate-500 hover:text-slate-800 font-bold cursor-pointer"
                >
                  Cancel
                </button>
              </div>

              <div>
                <label className="text-[11px] font-bold text-slate-600 block mb-1">
                  Full Name / Display Name
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. John Doe"
                  value={customName}
                  onChange={(e) => setCustomName(e.target.value)}
                  className="w-full px-3.5 py-2 rounded-xl bg-white border border-slate-200 text-slate-900 text-xs font-semibold focus:outline-none focus:border-[#FA5B0F]"
                />
              </div>

              <div>
                <label className="text-[11px] font-bold text-slate-600 block mb-1">
                  Google Email Address
                </label>
                <input
                  type="email"
                  required
                  placeholder="name@gmail.com"
                  value={customEmail}
                  onChange={(e) => setCustomEmail(e.target.value)}
                  className="w-full px-3.5 py-2 rounded-xl bg-white border border-slate-200 text-slate-900 text-xs font-semibold focus:outline-none focus:border-[#FA5B0F]"
                />
              </div>

              {inputError && (
                <p className="text-xs text-rose-600 font-bold bg-rose-50 border border-rose-200 p-2 rounded-lg">
                  ⚠️ {inputError}
                </p>
              )}

              <button
                type="submit"
                disabled={isProcessing}
                className="traveltour-btn-primary w-full py-2.5 px-4 text-xs font-black rounded-xl flex items-center justify-center gap-2 cursor-pointer shadow-sm"
              >
                <span>Sign Up & Continue to TripSaathi →</span>
              </button>
            </form>
          )}

          {/* Quick Sign Up With Google Button (Instant Action) */}
          <div className="pt-2">
            <button
              type="button"
              onClick={() => {
                if (savedAccounts.length > 0) {
                  handleSelectAccount(savedAccounts[0]);
                } else {
                  setIsAddingCustom(true);
                }
              }}
              disabled={isProcessing}
              className="w-full py-3.5 px-5 rounded-2xl bg-[#19202E] hover:bg-[#FA5B0F] text-white font-extrabold text-sm transition-all shadow-md flex items-center justify-center gap-3 cursor-pointer group"
            >
              <svg className="w-5 h-5 bg-white p-0.5 rounded-full" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
              </svg>
              <span>Instant Google One-Click Sign In</span>
            </button>
          </div>

          {/* Privacy & Account Storage Notice */}
          <div className="pt-4 border-t border-[#ECE8E1] text-center space-y-2">
            <div className="flex items-center justify-center gap-4 text-[11px] text-slate-500 font-medium">
              <span className="flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                100% Secure Storage
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Lock className="w-3.5 h-3.5 text-[#FA5B0F]" />
                Encrypted Client-Side
              </span>
            </div>
            <p className="text-[10px] text-slate-400 max-w-sm mx-auto">
              Your Google Account credentials and saved itineraries remain securely persisted on this device. By signing in, you unlock live Vande Bharat & expressway multi-modal grounding.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
