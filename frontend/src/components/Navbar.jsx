import React from 'react';
import { Compass, Sparkles, PlaneTakeoff, Bookmark, Globe, IndianRupee, Phone, Mail, Clock, LogOut, UserCheck, Users } from 'lucide-react';

export default function Navbar({ 
  activePage, 
  setActivePage, 
  onTriggerNewTrip, 
  savedCount,
  currentUser,
  onLogout,
  onSwitchAccount,
  onOpenAuthModal
}) {
  return (
    <header className="sticky top-0 z-40 transition-all shadow-xs">
      {/* TravelTour Top Sub-Bar */}
      <div className="bg-[#19202E] text-slate-300 text-[11px] py-1.5 px-4 sm:px-8 border-b border-slate-800">
        <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-4 sm:gap-6 flex-wrap">
            <span className="flex items-center gap-1.5 hover:text-white transition-colors">
              <Phone className="w-3 h-3 text-[#FA5B0F]" />
              <span className="font-semibold">+91 1800-TRIP-SAATHI</span>
            </span>
            <span className="hidden md:flex items-center gap-1.5 hover:text-white transition-colors">
              <Mail className="w-3 h-3 text-[#FA5B0F]" />
              <span>contact@tripsaathi.ai</span>
            </span>
            <span className="hidden lg:flex items-center gap-1.5 text-slate-400">
              <Clock className="w-3 h-3 text-[#FA5B0F]" />
              <span>Mon - Sun: 24/7 AI Real-Time Transit</span>
            </span>
          </div>

          <div className="flex items-center gap-3">
            {currentUser && (
              <span className="hidden sm:inline-flex items-center gap-1.5 text-[10px] font-bold bg-slate-800/90 text-slate-200 border border-slate-700 px-2 py-0.5 rounded-full">
                <svg className="w-3 h-3" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                </svg>
                <span>Google: {currentUser.name}</span>
              </span>
            )}
            <span className="inline-flex items-center gap-1 text-[10px] font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded-full">
              <IndianRupee className="w-2.5 h-2.5 text-[#FA5B0F]" />
              INR Grounded Fares
            </span>
          </div>
        </div>
      </div>

      {/* Main Navbar */}
      <div className="bg-white/95 backdrop-blur-md border-b border-[#ECE8E1]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-18 flex items-center justify-between gap-2">
          {/* Brand */}
          <div 
            onClick={() => setActivePage('showcase')}
            className="flex items-center gap-3.5 cursor-pointer group shrink-0"
          >
            <div className="w-11 h-11 rounded-2xl bg-[#FA5B0F] flex items-center justify-center text-white shadow-md shadow-[#FA5B0F]/25 group-hover:scale-105 transition-transform">
              <Compass className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-2xl font-black tracking-tight text-[#19202E] font-serif">
                  Trip<span className="text-[#FA5B0F]">Saathi</span>
                </span>
                <span className="text-[10px] font-extrabold uppercase tracking-wider bg-[#FFF4EE] text-[#FA5B0F] border border-[#FED7AA] px-2 py-0.5 rounded-md">
                  Tour AI
                </span>
              </div>
              <p className="text-[11px] text-slate-500 font-medium hidden md:block">
                Curated Grounded Journeys • Real Transit • Zero Repeated Stops
              </p>
            </div>
          </div>

          {/* Page Nav Tabs */}
          <nav className="flex items-center gap-1 sm:gap-2">
            <button
              onClick={() => setActivePage('showcase')}
              className={`px-3 sm:px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                activePage === 'showcase'
                  ? 'bg-[#19202E] text-white shadow-sm'
                  : 'text-slate-600 hover:text-[#FA5B0F] hover:bg-[#FFF4EE]'
              }`}
            >
              <Globe className={`w-4 h-4 ${activePage === 'showcase' ? 'text-[#FA5B0F]' : 'text-slate-500'}`} />
              <span>Discover & Tours</span>
            </button>

            <button
              onClick={() => setActivePage('planner')}
              className={`px-3 sm:px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                activePage === 'planner'
                  ? 'bg-[#19202E] text-white shadow-sm'
                  : 'text-slate-600 hover:text-[#FA5B0F] hover:bg-[#FFF4EE]'
              }`}
            >
              <Compass className={`w-4 h-4 ${activePage === 'planner' ? 'text-[#FA5B0F]' : 'text-slate-500'}`} />
              <span>Trip Planner</span>
            </button>

            <button
              onClick={() => setActivePage('history')}
              className={`px-3 sm:px-4 py-2 rounded-xl text-xs sm:text-sm font-bold transition-all cursor-pointer flex items-center gap-1.5 relative ${
                activePage === 'history'
                  ? 'bg-[#19202E] text-white shadow-sm'
                  : 'text-slate-600 hover:text-[#FA5B0F] hover:bg-[#FFF4EE]'
              }`}
            >
              <Bookmark className={`w-4 h-4 ${activePage === 'history' ? 'text-[#FA5B0F]' : 'text-slate-500'}`} />
              <span>Saved Tours</span>
              <span className="min-w-4 px-1 h-4 bg-[#FA5B0F] text-white text-[9px] font-black rounded-full flex items-center justify-center">
                {savedCount || 0}
              </span>
            </button>
          </nav>

          {/* Right Section: User Profile & New Trip Action */}
          <div className="flex items-center gap-2 sm:gap-3">
            {/* Authenticated Google Account Pill */}
            {currentUser ? (
              <div className="flex items-center gap-1.5 sm:gap-2">
                <div 
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-xl bg-slate-50 border border-slate-200 shadow-2xs group cursor-pointer"
                  onClick={onSwitchAccount}
                  title={`Signed in as ${currentUser.name} (${currentUser.email}). Click to switch Google account.`}
                >
                  <div className="relative">
                    <img
                      src={currentUser.avatar}
                      alt={currentUser.name}
                      className="w-7 h-7 rounded-full object-cover border-2 border-white shadow-xs"
                      onError={(e) => {
                        e.target.src = `https://ui-avatars.com/api/?name=${encodeURIComponent(currentUser.name)}&background=FA5B0F&color=fff`;
                      }}
                    />
                    <div className="absolute -bottom-0.5 -right-0.5 bg-white p-0.5 rounded-full shadow-2xs">
                      <svg className="w-2.5 h-2.5" viewBox="0 0 24 24">
                        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                      </svg>
                    </div>
                  </div>

                  <div className="hidden xl:block text-left">
                    <span className="text-xs font-black text-slate-800 block leading-tight truncate max-w-[110px]">
                      {currentUser.name}
                    </span>
                    <span className="text-[10px] text-emerald-600 font-bold block leading-none">
                      ✓ Google Verified
                    </span>
                  </div>
                </div>

                {/* Switch Google Account Button */}
                <button
                  type="button"
                  onClick={onSwitchAccount}
                  className="p-2 sm:px-2.5 sm:py-1.5 text-slate-700 hover:text-[#4285F4] hover:bg-sky-50 rounded-xl border border-slate-200 hover:border-sky-300 transition-colors cursor-pointer text-xs font-bold flex items-center gap-1.5"
                  title="Switch from one Google account to another"
                >
                  <Users className="w-3.5 h-3.5 text-[#4285F4]" />
                  <span className="hidden sm:inline">Switch Account</span>
                </button>

                {/* Logout Button */}
                <button
                  type="button"
                  onClick={onLogout}
                  className="p-2 sm:px-2.5 sm:py-1.5 text-slate-600 hover:text-rose-600 hover:bg-rose-50 rounded-xl border border-slate-200 hover:border-rose-200 transition-colors cursor-pointer text-xs font-bold flex items-center gap-1"
                  title="Sign out and choose Google account"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span className="hidden sm:inline">Sign Out</span>
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={onOpenAuthModal}
                className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white border border-slate-200 text-xs font-bold text-slate-700 hover:text-[#FA5B0F] hover:border-[#FA5B0F] transition-all shadow-xs cursor-pointer"
              >
                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
                </svg>
                <span className="hidden sm:inline">Sign In with Google</span>
              </button>
            )}

            {/* New Journey Button */}
            <button
              onClick={onTriggerNewTrip}
              className="traveltour-btn-primary text-xs sm:text-sm font-extrabold px-3.5 sm:px-4 py-2 sm:py-2.5 rounded-xl shadow-md transition-all cursor-pointer flex items-center gap-1.5 shrink-0"
              title="Starts plane takeoff and launches a fresh trip"
            >
              <PlaneTakeoff className="w-4 h-4" />
              <span className="hidden sm:inline">New Journey</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
