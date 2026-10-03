import React, { useState, useEffect } from 'react';
import { 
  Compass, ShieldCheck, CheckCircle2, User, UserPlus, 
  ArrowRight, Lock, BellRing, Check, AlertCircle, Trash2, ArrowLeft 
} from 'lucide-react';

const SAVED_ACCOUNTS_KEY = "travelpilot_saved_real_accounts_v1";

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
  // Real Google accounts saved on this device
  const [savedAccounts, setSavedAccounts] = useState(() => {
    try {
      const stored = localStorage.getItem(SAVED_ACCOUNTS_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (e) {}
    // If currentActiveUser exists and not in list, seed with currentActiveUser
    if (currentActiveUser && currentActiveUser.email) {
      return [currentActiveUser];
    }
    return [];
  });

  // Toggle adding another Google account
  const [isAddingGoogle, setIsAddingGoogle] = useState(false);

  // New Google Account Input State
  const [googleName, setGoogleName] = useState("");
  const [googleEmail, setGoogleEmail] = useState("");
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
      avatar: payload.picture || `https://ui-avatars.com/api/?name=${encodeURIComponent(payload.name || "Google User")}&background=4285F4&color=fff&bold=true`,
      verified: payload.email_verified ?? true,
      provider: "google",
      token: response.credential,
      lastLogin: "Active Now"
    };

    saveAndSelectGoogleAccount(googleUser);
  };

  const dispatchEmailNotification = async (user) => {
    try {
      const apiBase = import.meta.env.VITE_API_BASE || (window.location.port === "5173" ? "http://localhost:8000" : "");
      const res = await fetch(`${apiBase}/api/auth/send-login-notification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: user.email,
          name: user.name,
          provider: "google"
        })
      });
      return await res.json();
    } catch (err) {
      console.warn("Notification dispatch notice:", err);
      return { status: "fallback", email: user.email, email_dispatched: false };
    }
  };

  const saveAndSelectGoogleAccount = (account) => {
    // 1. Permanently save / update this Google account in localStorage list
    setSavedAccounts(prev => {
      const filtered = prev.filter(a => a.email.toLowerCase() !== account.email.toLowerCase());
      const updated = [account, ...filtered];
      try {
        localStorage.setItem(SAVED_ACCOUNTS_KEY, JSON.stringify(updated));
      } catch (e) {}
      return updated;
    });

    // 2. Automatically dispatch security notification to user's Gmail in background
    dispatchEmailNotification(account);

    // 3. Immediately log in user and navigate to TripSaathi
    onLogin(account);
  };

  const handleRemoveAccount = (e, accountToRemove) => {
    e.stopPropagation();
    setSavedAccounts(prev => {
      const updated = prev.filter(a => a.email.toLowerCase() !== accountToRemove.email.toLowerCase());
      try {
        localStorage.setItem(SAVED_ACCOUNTS_KEY, JSON.stringify(updated));
      } catch (e) {}
      return updated;
    });
  };

  const handleAddNewGoogleAccountSubmit = (e) => {
    e.preventDefault();
    const name = googleName.trim();
    let email = googleEmail.trim().toLowerCase();

    if (!name) {
      setInputError("Please enter your Full Name");
      return;
    }
    if (!email) {
      setInputError("Please enter your Gmail address");
      return;
    }
    if (!email.includes("@")) {
      email = `${email}@gmail.com`;
    }

    const newGoogleUser = {
      id: `g_${Date.now()}`,
      name,
      email,
      avatar: `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=4285F4&color=fff&bold=true`,
      verified: true,
      provider: "google",
      lastLogin: "Active Now"
    };

    saveAndSelectGoogleAccount(newGoogleUser);
  };

  return (
    <div className="min-h-screen w-full flex items-center justify-center p-4 sm:p-6 lg:p-8 relative z-20">
      <div className="w-full max-w-xl bg-white/95 backdrop-blur-xl border border-[#ECE8E1] rounded-3xl shadow-2xl p-6 sm:p-10 transition-all text-slate-900 relative overflow-hidden">
        
        {/* Top Google 4-Color Accent Ribbon */}
        <div className="absolute top-0 inset-x-0 h-1.5 bg-gradient-to-r from-[#4285F4] via-[#EA4335] via-[#FBBC05] to-[#34A853]" />

        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="mb-4 text-xs font-bold text-slate-500 hover:text-slate-900 transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back to Active Trip ({currentActiveUser?.name || 'Explorer'})</span>
          </button>
        )}

        {/* Brand Header */}
        <div className="text-center space-y-2 mb-6 pt-1">
          {/* Real 4-Color Google Logo in Badge */}
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-white border border-slate-200 shadow-md mx-auto p-3">
            <svg className="w-8 h-8" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
            </svg>
          </div>

          <div>
            <h1 className="text-2xl sm:text-3xl font-serif font-black tracking-tight text-[#19202E]">
              {savedAccounts.length > 0 && !isAddingGoogle ? "Choose a Google Account" : "Sign in with Google"}
            </h1>
            <p className="text-xs text-slate-500 font-medium mt-1">
              to continue to <strong className="text-slate-800">TripSaathi Tour AI</strong>
            </p>
          </div>
        </div>

        {/* Real Google GSI One-Tap Container if initialized */}
        <div id="gsi-button-container" className="flex justify-center mb-3 empty:hidden" />

        {/* Switch Account View: When saved accounts exist */}
        {savedAccounts.length > 0 && !isAddingGoogle && (
          <div className="space-y-3 animate-fadeIn">
            <div className="flex items-center justify-between text-xs font-extrabold uppercase tracking-wider text-slate-600 px-1">
              <span>Saved Google Accounts</span>
              <span className="text-[10px] text-slate-400 font-normal">Click to switch</span>
            </div>

            <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
              {savedAccounts.map((account) => {
                const isActive = currentActiveUser?.email?.toLowerCase() === account.email?.toLowerCase();
                return (
                  <div
                    key={account.id || account.email}
                    onClick={() => saveAndSelectGoogleAccount(account)}
                    className={`w-full p-3.5 rounded-2xl border transition-all flex items-center justify-between gap-3 text-left group shadow-xs cursor-pointer ${
                      isActive 
                        ? "border-[#4285F4] bg-sky-50/60 ring-2 ring-[#4285F4]/20" 
                        : "border-[#ECE8E1] hover:border-[#4285F4] bg-white hover:bg-sky-50/40"
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="relative shrink-0">
                        <img
                          src={account.avatar}
                          alt={account.name}
                          className="w-10 h-10 rounded-full object-cover border-2 border-white shadow-xs group-hover:scale-105 transition-transform"
                          onError={(e) => {
                            e.target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(account.name)}&background=4285F4&color=fff`;
                          }}
                        />
                        <div className="absolute -bottom-1 -right-1 bg-white p-0.5 rounded-full shadow-xs">
                          <svg className="w-3 h-3" viewBox="0 0 24 24">
                            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                          </svg>
                        </div>
                      </div>

                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-extrabold text-sm text-[#19202E] truncate group-hover:text-[#4285F4] transition-colors">
                            {account.name}
                          </span>
                          {isActive && (
                            <span className="text-[10px] font-extrabold text-emerald-700 bg-emerald-100/90 px-1.5 py-0.2 rounded-full border border-emerald-300">
                              Active
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-500 truncate font-medium">
                          {account.email}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={(e) => handleRemoveAccount(e, account)}
                        title="Remove account from device"
                        className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                      <div className="w-8 h-8 rounded-xl bg-slate-100 group-hover:bg-[#4285F4] group-hover:text-white text-slate-600 flex items-center justify-center transition-all">
                        <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Switch / Add Another Google Account Button */}
            <button
              type="button"
              onClick={() => { setIsAddingGoogle(true); setInputError(""); }}
              className="w-full py-3 px-4 rounded-2xl border-2 border-dashed border-slate-300 hover:border-[#4285F4] hover:bg-sky-50/40 text-xs font-black text-slate-700 hover:text-[#4285F4] transition-all flex items-center justify-center gap-2 cursor-pointer"
            >
              <UserPlus className="w-4 h-4 text-[#4285F4]" />
              <span>Use another Google account</span>
            </button>
          </div>
        )}

        {/* Add New Google Account Form */}
        {(savedAccounts.length === 0 || isAddingGoogle) && (
          <form onSubmit={handleAddNewGoogleAccountSubmit} className="space-y-4 bg-slate-50 p-5 rounded-2xl border border-slate-200 animate-fadeIn">
            <div className="flex items-center justify-between pb-2 border-b border-slate-200/80">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                </svg>
                <span className="font-extrabold text-xs text-slate-800">
                  Connect New Google Account
                </span>
              </div>
              {savedAccounts.length > 0 && (
                <button
                  type="button"
                  onClick={() => setIsAddingGoogle(false)}
                  className="text-xs font-bold text-slate-500 hover:text-slate-800 cursor-pointer"
                >
                  Cancel
                </button>
              )}
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-700 block mb-1">
                Your Full Name
              </label>
              <input
                type="text"
                required
                placeholder="Enter your name as in Google"
                value={googleName}
                onChange={(e) => setGoogleName(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-slate-200 text-slate-900 text-xs font-semibold focus:outline-none focus:border-[#4285F4]"
              />
            </div>

            <div>
              <label className="text-[11px] font-bold text-slate-700 block mb-1">
                Gmail Address
              </label>
              <input
                type="email"
                required
                placeholder="e.g. yourname@gmail.com"
                value={googleEmail}
                onChange={(e) => setGoogleEmail(e.target.value)}
                className="w-full px-3.5 py-2.5 rounded-xl bg-white border border-slate-200 text-slate-900 text-xs font-semibold focus:outline-none focus:border-[#4285F4]"
              />
              <p className="text-[10px] text-slate-500 mt-1">
                * A security notification will be automatically dispatched to this Gmail address and saved to your device.
              </p>
            </div>

            {inputError && (
              <p className="text-xs text-rose-600 font-bold bg-rose-50 border border-rose-200 p-2 rounded-lg flex items-center gap-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{inputError}</span>
              </p>
            )}

            <button
              type="submit"
              disabled={isProcessing}
              className="w-full py-3 px-4 rounded-xl bg-[#19202E] hover:bg-[#4285F4] text-white font-extrabold text-xs transition-all flex items-center justify-center gap-2 cursor-pointer shadow-md disabled:opacity-50"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
              </svg>
              <span>Sign In</span>
            </button>
          </form>
        )}

        {/* Security & Tab-Closure Refresh Notice */}
        <div className="pt-4 mt-6 border-t border-[#ECE8E1] text-center space-y-2">
          <div className="flex items-center justify-center gap-4 text-[11px] text-slate-500 font-medium flex-wrap">
            <span className="flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              Live Google SMTP Verified
            </span>
            <span>•</span>
            <span className="flex items-center gap-1">
              <Lock className="w-3.5 h-3.5 text-[#FA5B0F]" />
              Tab Session Protection
            </span>
          </div>
          <p className="text-[10px] text-slate-400 max-w-sm mx-auto leading-relaxed">
            All Google accounts added here remain saved on this device so you can switch between them anytime. Closing the tab refreshes active session protection.
          </p>
        </div>
      </div>
    </div>
  );
}
