import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import IndianFlagBackground from './components/IndianFlagBackground';
import HALTejasTakeoffAnimation from './components/HALTejasTakeoffAnimation';
import AirplaneAnimation5s from './components/AirplaneAnimation5s';
import ShowcasePage from './components/ShowcasePage';
import TripForm from './components/TripForm';
import TimelineView from './components/TimelineView';
import TransportationCard from './components/TransportationCard';
import ChatPanel from './components/ChatPanel';
import Dashboard from './components/Dashboard';
import HistoryPage from './components/HistoryPage';
import PlaceDetailPage from './components/PlaceDetailPage';
import AlreadySelectedModal from './components/AlreadySelectedModal';
import RefreshSavePromptModal from './components/RefreshSavePromptModal';
import TransportationPage from './components/TransportationPage';
import Footer from './components/Footer';
import NamasteAvatar from './components/NamasteAvatar';
import GoogleAuthPage from './components/GoogleAuthPage';
import { 
  Sparkles, Compass, MapPin, Calendar, IndianRupee, 
  ShieldCheck, AlertCircle, PlayCircle, Users, Bookmark, Check,
  Bot, MessageSquare, TrendingUp, SlidersHorizontal, ChevronDown, ChevronUp, X, BarChart3, ArrowLeft 
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || (window.location.port === "5173" ? "http://localhost:8000" : "");
const API_BASE_FALLBACK = import.meta.env.VITE_API_BASE || (window.location.port === "5173" ? "http://127.0.0.1:8000" : "");
const STORAGE_KEY = "travelpilot_saved_trips_v2";
const DRAFT_STORAGE_KEY = "travelpilot_active_draft_v2";
const AUTH_STORAGE_KEY = "travelpilot_google_user_v1";

async function safeApiFetch(endpoint, options = {}) {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, options);
    return res;
  } catch (err) {
    console.warn("Primary API host failed, trying fallback 127.0.0.1:8000...", err);
    return await fetch(`${API_BASE_FALLBACK}${endpoint}`, options);
  }
}

export default function App() {
  const [activePage, setActivePage] = useState('showcase'); // 'showcase' | 'planner' | 'history'
  const [itinerary, setItinerary] = useState(null);
  const [selectedStopForDetails, setSelectedStopForDetails] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [cancellingStopId, setCancellingStopId] = useState(null);
  const [disruptionData, setDisruptionData] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [isUpdatingConstraints, setIsUpdatingConstraints] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [isPlaneFlying, setIsPlaneFlying] = useState(false);
  const [airplaneAnimation, setAirplaneAnimation] = useState(null);
  const [duplicateModal, setDuplicateModal] = useState({ isOpen: false, existingTrip: null, criteria: null, onProceedAnyway: null });
  const [saveToast, setSaveToast] = useState(null);
  const [isViewingTransportPage, setIsViewingTransportPage] = useState(false);
  const [transportPageParams, setTransportPageParams] = useState(null);
  const [refreshPromptModal, setRefreshPromptModal] = useState({ isOpen: false, trip: null });
  const [showDashboardSection, setShowDashboardSection] = useState(false);
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);

  // Authenticated User State (Stored in sessionStorage so session refreshes when user closes tab)
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const stored = sessionStorage.getItem(AUTH_STORAGE_KEY);
      if (stored) return JSON.parse(stored);
    } catch (e) {}
    return null;
  });
  const [isSwitchingAccount, setIsSwitchingAccount] = useState(false);

  const handleGoogleLogin = (user) => {
    setCurrentUser(user);
    setIsSwitchingAccount(false);
    try {
      sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
    } catch (e) {}
    setSaveToast(`Welcome, ${user.name}! Security notification sent automatically to ${user.email}`);
    setTimeout(() => setSaveToast(null), 3500);
  };

  const handleGoogleLogout = () => {
    setCurrentUser(null);
    setIsSwitchingAccount(false);
    try {
      sessionStorage.removeItem(AUTH_STORAGE_KEY);
    } catch (e) {}
    setSaveToast("Signed out.");
    setTimeout(() => setSaveToast(null), 2500);
  };

  const todayStr = new Date().toISOString().split('T')[0];
  const defaultEnd = new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

  // Persistent Trip Planner Form Draft across page switches, transport browser & back navigation
  const [tripFormData, setTripFormData] = useState(() => {
    try {
      const stored = localStorage.getItem("travelpilot_form_draft_v2");
      if (stored) return JSON.parse(stored);
    } catch (e) {}
    return {
      origin: "",
      destination: "",
      startDate: todayStr,
      endDate: defaultEnd,
      budget: 15000,
      membersCount: 2,
      travelMode: "road",
      selectedInterests: ["Landmarks", "Art & Culture", "Food & Dining"]
    };
  });

  useEffect(() => {
    try {
      localStorage.setItem("travelpilot_form_draft_v2", JSON.stringify(tripFormData));
    } catch (e) {}
  }, [tripFormData]);

  // Persistent History from localStorage
  const [savedTrips, setSavedTrips] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch (e) {
      console.error("Error reading saved trips:", e);
      return [];
    }
  });

  // Save to localStorage on change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(savedTrips));
    } catch (e) {
      console.error("Error saving trips to localStorage:", e);
    }
  }, [savedTrips]);

  // Check if two trips have identical criteria (destination, members, budget, transport, dates)
  const isSameTripCriteria = (tripA, tripB) => {
    if (!tripA || !tripB) return false;
    const metaA = tripA.metadata || tripA;
    const metaB = tripB.metadata || tripB;

    const destA = (metaA.destination || "").trim().toLowerCase();
    const destB = (metaB.destination || "").trim().toLowerCase();
    if (!destA || !destB || destA !== destB) return false;

    const membersA = Number(metaA.members_count || 1);
    const membersB = Number(metaB.members_count || 1);
    if (membersA !== membersB) return false;

    const budgetA = Number(metaA.budget || 0);
    const budgetB = Number(metaB.budget || 0);
    if (budgetA !== budgetB) return false;

    const modeA = (metaA.travel_mode || "road").toLowerCase();
    const modeB = (metaB.travel_mode || "road").toLowerCase();
    if (modeA !== modeB) return false;

    return true;
  };

  // Helper to save a trip or monument exploration into persistent history without duplicate criteria
  const archiveTrip = (itin, monumentName = null, notifyDuplicate = false) => {
    if (!itin) return false;

    const existingDuplicate = savedTrips.find((t) => isSameTripCriteria(t, itin));
    if (existingDuplicate) {
      if (notifyDuplicate) {
        setDuplicateModal({
          isOpen: true,
          existingTrip: existingDuplicate,
          criteria: itin.metadata || itin,
          onProceedAnyway: null
        });
      }
      return false;
    }

    const uniqueId = itin.id || itin.trip_id || `saved_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
    const tripRecord = {
      ...itin,
      id: uniqueId,
      trip_id: uniqueId,
      monument_name: monumentName || itin.monument_name || itin.metadata?.destination || "Custom Itinerary",
      saved_at: itin.saved_at || new Date().toISOString(),
      personal_notes: itin.personal_notes || ""
    };

    setSavedTrips((prev) => [tripRecord, ...prev]);
    setSaveToast(`Trip to ${itin.metadata?.destination || 'destination'} saved to history!`);
    setTimeout(() => setSaveToast(null), 3500);
    return true;
  };

  const handleSaveCurrentTrip = () => {
    if (!itinerary) return;
    const existingDuplicate = savedTrips.find((t) => isSameTripCriteria(t, itinerary));
    if (existingDuplicate) {
      setDuplicateModal({
        isOpen: true,
        existingTrip: existingDuplicate,
        criteria: itinerary.metadata || itinerary,
        onProceedAnyway: () => {
          archiveTrip(itinerary, itinerary.metadata?.destination, false);
          setActivePage('history');
        }
      });
    } else {
      archiveTrip(itinerary, itinerary.metadata?.destination, true);
      setActivePage('history');
    }
  };

  const handleTriggerNewTrip = () => {
    setIsPlaneFlying(true);
  };

  const handlePlaneAnimationComplete = () => {
    setIsPlaneFlying(false);
    setItinerary(null);
    setDisruptionData(null);
    setIsViewingTransportPage(false);
    setSelectedStopForDetails(null);
    try {
      localStorage.removeItem(DRAFT_STORAGE_KEY);
    } catch (e) {}
    setActivePage('planner');
  };

  const handleGenerate = async (formData, monumentName = null) => {
    // Launch 5-second High-Resolution Airplane Animation (IgniteMotion YwEPRJVV7V8)
    if (formData?.destination) {
      setAirplaneAnimation({
        destination: formData.destination,
        origin: formData.origin || "Delhi"
      });
    }

    setIsLoading(true);
    setApiError(null);
    setDisruptionData(null);
    setIsViewingTransportPage(false);
    setSelectedStopForDetails(null);
    setActivePage('planner');

    try {
      const res = await safeApiFetch('/itinerary/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      if (!res.ok) {
        throw new Error(`Server returned status ${res.status}`);
      }
      const data = await res.json();
      setItinerary(data);
      archiveTrip(data, monumentName, false);

      setChatMessages([
        {
          role: 'agent',
          text: `Namaste! I have crafted a ${data.days.length}-day trip to ${data.metadata.destination} for ${data.metadata.members_count} member(s). Verified ${data.metadata.travel_mode.toUpperCase()} transit: ${data.metadata.transportation?.route_name || 'Highway Corridor'}. Total estimated cost is ₹${data.trip_totals.estimated_total_cost.toLocaleString('en-IN')}. How can I assist you with this itinerary?`
        }
      ]);
      setActivePage('planner');
    } catch (err) {
      console.error("Generate error:", err);
      setApiError("Could not connect to TripSaathi backend on http://localhost:8000 or http://127.0.0.1:8000. Please ensure the backend is running.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectMonumentFromShowcase = (destinationCity, monumentName, originCity, members) => {
    const todayStr = new Date().toISOString().split('T')[0];
    const defaultEnd = new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

    const candidate = {
      origin: originCity || "Delhi",
      destination: destinationCity,
      start_date: todayStr,
      end_date: defaultEnd,
      budget: 18000,
      members_count: members || 2,
      travel_mode: "road",
      interests: ["Landmarks", "Art & Culture", "Food & Dining"]
    };

    setIsViewingTransportPage(false);
    setSelectedStopForDetails(null);
    setActivePage('planner');

    // Trigger high-resolution 5-second airplane animation
    setAirplaneAnimation({
      destination: destinationCity,
      origin: originCity || "Delhi"
    });

    handleGenerate(candidate, monumentName);
  };

  const handleCancelStop = async (stopId, reason) => {
    if (!itinerary) return;
    setCancellingStopId(stopId);
    setApiError(null);
    try {
      const res = await safeApiFetch('/itinerary/disrupt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          itinerary,
          stop_id: stopId,
          reason: reason || "User cancelled activity"
        })
      });
      if (!res.ok) {
        throw new Error(`Disruption endpoint error: ${res.status}`);
      }
      const data = await res.json();
      setItinerary(data.updated_itinerary);
      archiveTrip(data.updated_itinerary);

      setDisruptionData({
        summary: data.summary,
        affectedDay: data.affected_day,
        alternativeName: data.alternative_suggested
      });

      setChatMessages(prev => [
        ...prev,
        {
          role: 'agent',
          text: `⚡ Disruption Handled: ${data.summary}`
        }
      ]);
    } catch (err) {
      console.error("Disrupt error:", err);
      setApiError("Failed to disrupt and rebuild activity.");
    } finally {
      setCancellingStopId(null);
    }
  };

  const handleSendMessage = async (msgText) => {
    if (!itinerary) return;
    setChatMessages(prev => [...prev, { role: 'user', text: msgText }]);
    setIsChatLoading(true);
    setApiError(null);

    try {
      const res = await safeApiFetch('/itinerary/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          itinerary,
          message: msgText,
          history: chatMessages.slice(-8)
        })
      });
      if (!res.ok) {
        throw new Error(`Chat error: ${res.status}`);
      }
      const data = await res.json();
      setChatMessages(prev => [...prev, { role: 'agent', text: data.reply }]);

      if (data.updated_itinerary) {
        setItinerary(data.updated_itinerary);
        archiveTrip(data.updated_itinerary);
        setDisruptionData({
          summary: data.reply,
          affectedDay: null,
          alternativeName: null
        });
      }
    } catch (err) {
      console.error("Chat error:", err);
      setChatMessages(prev => [
        ...prev,
        { role: 'agent', text: "Sorry, I ran into an error connecting to the trip context. Please verify the backend is running." }
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleUpdateConstraints = async (constraintData) => {
    if (!itinerary) return;
    setIsUpdatingConstraints(true);
    setApiError(null);

    try {
      const res = await safeApiFetch('/itinerary/update-constraints', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          itinerary,
          ...constraintData
        })
      });
      if (!res.ok) throw new Error(`Update constraints error: ${res.status}`);
      const data = await res.json();
      setItinerary(data.updated_itinerary);
      archiveTrip(data.updated_itinerary);

      setDisruptionData({
        summary: `Trip Constraints Updated: ${data.summary}`,
        affectedDay: null,
        alternativeName: null
      });
      setChatMessages(prev => [
        ...prev,
        { role: 'agent', text: `Synchronized constraints. ${data.summary}` }
      ]);
    } catch (err) {
      console.error("Constraint update error:", err);
      setApiError("Failed to update constraints.");
    } finally {
      setIsUpdatingConstraints(false);
    }
  };

  // On mount: detect if page was refreshed, and show the 'Want to save history or not' popup
  useEffect(() => {
    let wasRefreshed = false;
    try {
      const perfEntries = window.performance?.getEntriesByType?.('navigation');
      if (perfEntries && perfEntries.length > 0 && perfEntries[0].type === 'reload') {
        wasRefreshed = true;
      } else if (window.performance?.navigation?.type === 1) {
        wasRefreshed = true;
      } else if (sessionStorage.getItem('travelpilot_page_reloaded') === 'true') {
        wasRefreshed = true;
      }
      sessionStorage.removeItem('travelpilot_page_reloaded');
    } catch (e) {
      console.error("Error checking reload state:", e);
    }

    let hasSavedTrips = false;
    let savedList = [];
    try {
      const rawSaved = localStorage.getItem(STORAGE_KEY);
      if (rawSaved) {
        const parsed = JSON.parse(rawSaved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          hasSavedTrips = true;
          savedList = parsed;
        }
      }
    } catch (e) {}

    let storedDraft = null;
    try {
      const rawDraft = localStorage.getItem(DRAFT_STORAGE_KEY);
      if (rawDraft) storedDraft = JSON.parse(rawDraft);
    } catch (e) {}

    // Only show refresh modal if page was refreshed AND there are actually trips saved in history
    if (wasRefreshed && hasSavedTrips) {
      setRefreshPromptModal({
        isOpen: true,
        trip: storedDraft || (savedList.length > 0 ? savedList[0] : null)
      });
    } else if (storedDraft && storedDraft.metadata) {
      setItinerary(storedDraft);
    }
  }, []);

  // Sync active draft to localStorage
  useEffect(() => {
    if (itinerary) {
      try {
        localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(itinerary));
      } catch (e) {
        console.error("Error setting active draft:", e);
      }
    } else {
      try {
        localStorage.removeItem(DRAFT_STORAGE_KEY);
      } catch (e) {}
    }
  }, [itinerary]);

  // Beforeunload listener: flags that page is refreshing and preserves draft
  useEffect(() => {
    const handleBeforeUnload = () => {
      try {
        sessionStorage.setItem('travelpilot_page_reloaded', 'true');
        if (itinerary) {
          localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(itinerary));
        }
      } catch (err) {}
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [itinerary]);

  // If user selects 'Yes' on refresh popup: save the history!
  const handleRefreshSelectYes = () => {
    if (refreshPromptModal.trip) {
      archiveTrip(refreshPromptModal.trip, null, false);
      setItinerary(refreshPromptModal.trip);
      setActivePage('planner');
    }
    setRefreshPromptModal({ isOpen: false, trip: null });
    setSaveToast("History saved successfully!");
    setTimeout(() => setSaveToast(null), 3500);
  };

  // If user selects 'No' on refresh popup: delete the save history!
  const handleRefreshSelectNo = () => {
    setSavedTrips([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(DRAFT_STORAGE_KEY);
    } catch (e) {}
    setItinerary(null);
    setRefreshPromptModal({ isOpen: false, trip: null });
    setSaveToast("Saved history deleted.");
    setTimeout(() => setSaveToast(null), 3500);
  };

  const handleOpenTransportPage = (mode) => {
    if (!itinerary) return;
    setTransportPageParams({
      destination: itinerary.metadata.destination,
      origin: itinerary.metadata.origin || "Vadodara",
      travelDate: itinerary.metadata.start_date,
      initialMode: mode || itinerary.metadata.travel_mode || "road",
      membersCount: itinerary.metadata.members_count || 1,
      currentTransportation: itinerary.metadata.transportation,
      fromForm: false
    });
    setIsViewingTransportPage(true);
  };

  const handleOpenTransportPageFromForm = (params) => {
    const orig = (params.origin !== undefined ? params.origin : tripFormData.origin || "").trim();
    const dest = (params.destination !== undefined ? params.destination : tripFormData.destination || "").trim();
    const mode = params.travelMode || tripFormData.travelMode || "road";

    setTripFormData(prev => ({
      ...prev,
      origin: orig,
      destination: dest,
      travelMode: mode,
      startDate: params.startDate || prev.startDate,
      membersCount: params.membersCount || prev.membersCount
    }));

    // If either orig or dest is empty, never open transport page or show fallback Vadodara to Agra!
    if (!orig || !dest) {
      setIsViewingTransportPage(false);
      return;
    }

    setTransportPageParams({
      destination: dest,
      origin: orig,
      travelDate: params.startDate || tripFormData.startDate,
      initialMode: mode,
      membersCount: params.membersCount || tripFormData.membersCount || 1,
      currentTransportation: null,
      fromForm: true
    });
    setIsViewingTransportPage(true);
  };

  const handleTransportModeChange = (newMode) => {
    setTripFormData(prev => ({ ...prev, travelMode: newMode }));
  };

  const handleSelectTransportationOption = (updatedTrans) => {
    setTripFormData(prev => ({ ...prev, travelMode: updatedTrans.mode }));

    if (itinerary) {
      const oldTransCost = itinerary.trip_totals?.transport_cost || 0;
      const newTransCost = updatedTrans.total_transit_cost || 0;
      const currentTotal = itinerary.trip_totals?.estimated_total_cost || 0;
      const newTotal = Math.max(0, currentTotal - oldTransCost + newTransCost);

      const updatedItin = {
        ...itinerary,
        metadata: {
          ...itinerary.metadata,
          travel_mode: updatedTrans.mode,
          transportation: updatedTrans
        },
        trip_totals: {
          ...itinerary.trip_totals,
          transport_cost: newTransCost,
          estimated_total_cost: newTotal
        }
      };

      setItinerary(updatedItin);
      archiveTrip(updatedItin);
      setChatMessages(prev => [
        ...prev,
        {
          role: 'agent',
          text: `🚆 Selected verified transit: ${updatedTrans.route_name} (${updatedTrans.verified_schedule || ''}). Updated total transit fare to ₹${newTransCost.toLocaleString('en-IN')}.`
        }
      ]);
      setSaveToast(`Selected ${updatedTrans.route_name}! Transit synchronized.`);
      setTimeout(() => setSaveToast(null), 3500);
    } else {
      setSaveToast(`Selected ${updatedTrans.route_name} for ₹${(updatedTrans.total_transit_cost || 0).toLocaleString('en-IN')}`);
      setTimeout(() => setSaveToast(null), 3500);
    }
    setIsViewingTransportPage(false);
  };

  const handleNavigatePage = (page) => {
    setIsViewingTransportPage(false);
    setSelectedStopForDetails(null);
    setActivePage(page);
  };

  const handleReloadTripFromHistory = (savedTrip) => {
    setItinerary(savedTrip);
    setDisruptionData(null);
    setIsViewingTransportPage(false);
    setSelectedStopForDetails(null);
    setActivePage('planner');
  };

  const handleDeleteTripFromHistory = (tripId, tripIndex) => {
    setSavedTrips(prev => {
      const updated = prev.filter((t, idx) => {
        const id = t.id || t.trip_id;
        if (tripId && id === tripId) return false;
        if (typeof tripIndex === 'number' && idx === tripIndex) return false;
        return true;
      });
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      } catch (e) {
        console.error("Error saving updated trips to localStorage:", e);
      }
      return updated;
    });
    setSaveToast("Trip deleted from history.");
    setTimeout(() => setSaveToast(null), 2500);
  };

  const handleDeleteAllTrips = () => {
    setSavedTrips([]);
    try {
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(DRAFT_STORAGE_KEY);
    } catch (e) {
      console.error("Error clearing saved history from localStorage:", e);
    }
    setSaveToast("All saved trips deleted.");
    setTimeout(() => setSaveToast(null), 2500);
  };

  const handleUpdateNotesInHistory = (tripId, notes) => {
    setSavedTrips(prev => prev.map(t => {
      if ((t.trip_id || t.id) === tripId) {
        return { ...t, personal_notes: notes };
      }
      return t;
    }));
  };

  // When user visits without being logged in (or chooses to switch accounts):
  // Show the Google Authentication Sign-Up / Accounts selection page first
  if (!currentUser || isSwitchingAccount) {
    return (
      <div className="min-h-screen text-slate-900 flex flex-col selection:bg-orange-100 selection:text-orange-900 relative">
        {/* High-Resolution Mountain Lake Background */}
        <IndianFlagBackground />

        {/* Floating toast notification */}
        {saveToast && (
          <div className="fixed top-6 right-6 z-50 bg-[#19202E] text-white font-extrabold text-xs px-4 py-3 rounded-2xl shadow-xl flex items-center gap-2 animate-bounce border border-slate-700">
            <Check className="w-4 h-4 text-[#FA5B0F]" />
            <span>{saveToast}</span>
          </div>
        )}

        <GoogleAuthPage 
          onLogin={handleGoogleLogin} 
          onCancel={currentUser ? () => setIsSwitchingAccount(false) : null}
          currentActiveUser={currentUser}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen text-slate-900 flex flex-col selection:bg-orange-100 selection:text-orange-900 relative">
      {/* Indian Flag Watermark Background */}
      <IndianFlagBackground />

      {/* 2-Second Full-Screen High-Resolution Airplane Animation with Clouds (IgniteMotion YwEPRJVV7V8) */}
      {airplaneAnimation && (
        <AirplaneAnimation5s
          onComplete={() => setAirplaneAnimation(null)}
        />
      )}

      {/* Soaring HAL Tejas Takeoff Animation with Atithi Devo Bhava Reload */}
      {isPlaneFlying && (
        <HALTejasTakeoffAnimation onComplete={handlePlaneAnimationComplete} />
      )}

      {/* Top Navbar */}
      <Navbar 
        activePage={activePage}
        setActivePage={handleNavigatePage}
        onTriggerNewTrip={handleTriggerNewTrip}
        savedCount={savedTrips.length}
        currentUser={currentUser}
        onLogout={handleGoogleLogout}
        onSwitchAccount={() => setIsSwitchingAccount(true)}
        onOpenAuthModal={() => setIsSwitchingAccount(true)}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 relative z-10 space-y-8">
        {/* Global Error Banner */}
        {apiError && (
          <div className="bg-rose-50 border border-rose-200 rounded-2xl p-4 flex items-center gap-3 text-rose-800 text-sm shadow-sm">
            <AlertCircle className="w-5 h-5 text-rose-600 shrink-0" />
            <div className="flex-1">{apiError}</div>
            <button 
              onClick={() => setApiError(null)} 
              className="text-xs font-bold text-rose-700 hover:underline cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* DEDICATED TRANSPORTATION OPTIONS PAGE (Road Ola/Uber, Railway IRCTC, Flight) */}
        {isViewingTransportPage ? (
          <TransportationPage 
            destination={transportPageParams?.destination || itinerary?.metadata?.destination || tripFormData.destination || ""}
            origin={transportPageParams?.origin || itinerary?.metadata?.origin || tripFormData.origin || ""}
            travelDate={transportPageParams?.travelDate || itinerary?.metadata?.start_date || tripFormData.startDate}
            initialMode={transportPageParams?.initialMode || itinerary?.metadata?.travel_mode || tripFormData.travelMode || "road"}
            membersCount={transportPageParams?.membersCount || itinerary?.metadata?.members_count || tripFormData.membersCount || 1}
            currentTransportation={transportPageParams?.currentTransportation || itinerary?.metadata?.transportation}
            fromForm={transportPageParams?.fromForm}
            onBack={() => setIsViewingTransportPage(false)}
            onSelectOption={handleSelectTransportationOption}
            onModeChange={handleTransportModeChange}
          />
        ) : (
          <>
            {/* PAGE 1: SHOWCASE & MONUMENTS */}
            {activePage === 'showcase' && (
              <ShowcasePage 
                onSelectDestination={handleSelectMonumentFromShowcase}
                onStartPlanner={() => handleNavigatePage('planner')}
              />
            )}

            {/* PAGE 2: TRIP PLANNER & TIMELINE */}
            {activePage === 'planner' && (
              <div className="space-y-8">
                {!itinerary ? (
                  <div className="max-w-3xl mx-auto w-full">
                    <TripForm 
                      formData={tripFormData}
                      onChangeFormData={setTripFormData}
                      onGenerate={handleGenerate} 
                      isLoading={isLoading} 
                      onOpenTransportPage={handleOpenTransportPageFromForm}
                    />
                  </div>
                ) : (
                  /* Active Itinerary View */
                  <div className="space-y-6">
                    {/* Left Corner: Back and Trip Copilot AI Live */}
                    <div className="flex items-center justify-start gap-3 flex-wrap">
                      <button
                        type="button"
                        onClick={() => {
                          setItinerary(null);
                          setSelectedStopForDetails(null);
                        }}
                        className="flex items-center gap-2 px-4 py-2 bg-white hover:bg-slate-50 text-slate-800 hover:text-slate-950 font-extrabold text-xs rounded-xl border border-slate-200 hover:border-slate-300 transition-all shadow-xs cursor-pointer group"
                        title="Back to planner"
                      >
                        <ArrowLeft className="w-4 h-4 text-slate-500 group-hover:-translate-x-1 transition-transform" />
                        <span>← Back to Trip Planner</span>
                      </button>

                      {/* Namaste AI Live placed on the Left Corner */}
                      <button
                        type="button"
                        onClick={() => setIsCopilotOpen(true)}
                        className="flex items-center gap-2.5 px-4 py-2 bg-gradient-to-r from-amber-600 via-orange-600 to-rose-600 hover:from-amber-700 hover:to-rose-700 text-white font-extrabold text-xs rounded-xl border border-orange-400/50 shadow-sm hover:shadow-md transition-all cursor-pointer"
                        title="Open Namaste AI assistant"
                      >
                        <NamasteAvatar size={22} className="shadow-xs" />
                        <span>Namaste AI</span>
                        <span className="bg-white/25 text-[10px] px-1.5 py-0.5 rounded-md text-white font-black">AI</span>
                      </button>
                    </div>

                    {/* Destination & Meta Strip */}
                    <div className="flex items-center justify-between flex-wrap gap-4 bg-white border border-slate-200/80 rounded-2xl px-6 py-4 shadow-xs card-3d">
                      <div className="flex items-center gap-4 flex-wrap">
                        <div className="flex items-center gap-2 text-sm font-extrabold text-slate-900">
                          <MapPin className="w-4 h-4 text-sky-600" />
                          <span>
                            {itinerary.metadata.origin && !itinerary.metadata.destination.toLowerCase().includes(itinerary.metadata.origin.toLowerCase()) 
                              ? `${itinerary.metadata.origin} → ${itinerary.metadata.destination}` 
                              : itinerary.metadata.destination}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-600 bg-slate-100 px-3 py-1 rounded-lg">
                          <Calendar className="w-3.5 h-3.5 text-slate-500" />
                          <span>{itinerary.metadata.start_date} → {itinerary.metadata.end_date}</span>
                        </div>
                        <div className="flex items-center gap-2 text-xs font-semibold text-indigo-700 bg-indigo-50 border border-indigo-200 px-3 py-1 rounded-lg">
                          <Users className="w-3.5 h-3.5 text-indigo-600" />
                          <span>{itinerary.metadata.members_count} Member(s)</span>
                        </div>
                        {itinerary.trip_totals?.estimated_total_cost > itinerary.metadata.budget ? (
                          <div className="flex items-center gap-2 text-xs font-bold text-rose-700 bg-rose-50 border border-rose-200 px-3 py-1 rounded-lg">
                            <IndianRupee className="w-3.5 h-3.5 text-rose-600" />
                            <span>Budget: ₹{itinerary.metadata.budget?.toLocaleString('en-IN')}</span>
                            <span className="text-[10px] font-black uppercase text-rose-700 bg-rose-100 px-1.5 py-0.5 rounded-md">Irrelevant Budget</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-lg">
                            <IndianRupee className="w-3.5 h-3.5 text-emerald-600" />
                            <span>Budget: ₹{itinerary.metadata.budget?.toLocaleString('en-IN')}</span>
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-2.5 flex-wrap">
                        {/* Selectable Trip Dashboard & Financial Analysis Button */}
                        <button
                          type="button"
                          onClick={() => setShowDashboardSection(!showDashboardSection)}
                          className={`flex items-center gap-1.5 px-4 py-2 font-extrabold text-xs rounded-xl border transition-all cursor-pointer shadow-xs ${
                            showDashboardSection
                              ? 'bg-gradient-to-r from-emerald-600 to-teal-700 text-white border-emerald-600 shadow-md shadow-emerald-500/20'
                              : 'bg-gradient-to-r from-emerald-50 to-teal-50 hover:from-emerald-600 hover:to-teal-600 text-emerald-800 hover:text-white border-emerald-200 hover:border-emerald-600'
                          }`}
                          title="Open or close Financial Dashboard and Constraint Settings"
                        >
                          <BarChart3 className="w-3.5 h-3.5 text-emerald-400" />
                          <span>{showDashboardSection ? 'Hide Dashboard & Financial Analysis' : 'Trip Dashboard & Financial Analysis'}</span>
                          <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showDashboardSection ? 'rotate-180' : ''}`} />
                        </button>
                      </div>
                    </div>


                    {/* Live Transportation Card */}
                    {itinerary.metadata.transportation && (
                      <TransportationCard 
                        transportation={itinerary.metadata.transportation}
                        membersCount={itinerary.metadata.members_count}
                        onSwitchMode={(newMode) => handleUpdateConstraints({ new_travel_mode: newMode })}
                        onOpenTransportPage={handleOpenTransportPage}
                      />
                    )}

                    {/* SELECTABLE SECTION: Trip Dashboard & Financial Analysis (shown only when selected) */}
                    {showDashboardSection && (
                      <div className="bg-white border-2 border-emerald-300/80 rounded-3xl p-6 sm:p-8 shadow-lg transition-all card-3d animate-in fade-in-50 duration-300">
                        <div className="flex items-center justify-between pb-4 mb-6 border-b border-emerald-100">
                          <div className="flex items-center gap-2.5">
                            <div className="w-9 h-9 rounded-2xl bg-emerald-100 text-emerald-800 flex items-center justify-center font-bold">
                              <BarChart3 className="w-5 h-5" />
                            </div>
                            <div>
                              <h3 className="text-base font-extrabold text-slate-900">
                                Trip Dashboard & Financial Analysis
                              </h3>
                              <p className="text-xs text-slate-500 font-medium">
                                Real-time group financial breakdown in INR (₹) and dynamic budget constraint sliders.
                              </p>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => setShowDashboardSection(false)}
                            className="text-xs font-extrabold text-slate-500 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-xl transition-all cursor-pointer"
                          >
                            Close Section ✕
                          </button>
                        </div>

                        <Dashboard 
                          itinerary={itinerary}
                          onUpdateConstraints={handleUpdateConstraints}
                          isUpdating={isUpdatingConstraints}
                        />
                      </div>
                    )}

                    {/* If user clicked a place to view real photos & reviews */}
                    {selectedStopForDetails ? (
                      <PlaceDetailPage 
                        stop={selectedStopForDetails}
                        destinationCity={itinerary.metadata.destination}
                        onBack={() => setSelectedStopForDetails(null)}
                        onBookmark={(stop, details) => {
                          archiveTrip({
                            ...itinerary,
                            id: `place_${stop.id}`,
                            monument_name: stop.activity,
                            personal_notes: `Saved landmark: ${details.name} in ${details.city}. Entry: ${details.ticketPriceINR > 0 ? `₹${details.ticketPriceINR}` : 'Free Entry'}. Rating: ${details.rating}★`
                          }, stop.activity);
                        }}
                      />
                    ) : (
                      /* Full-Width Spacious Timeline View */
                      <div className="w-full">
                        <TimelineView 
                          itinerary={itinerary} 
                          onCancelStop={handleCancelStop}
                          cancellingStopId={cancellingStopId}
                          onSelectStop={(stop) => setSelectedStopForDetails(stop)}
                        />
                      </div>
                    )}
                  </div>
            )}
          </div>
        )}

        {/* PAGE 3: PERSISTENT SAVED HISTORY */}
        {activePage === 'history' && (
          <HistoryPage 
            savedTrips={savedTrips}
            currentTrip={itinerary}
            onReloadTrip={handleReloadTripFromHistory}
            onOpenSelectedTrip={(trip) => {
              if (trip) {
                setItinerary(trip);
              }
              setActivePage('planner');
            }}
            onDeleteTrip={handleDeleteTripFromHistory}
            onDeleteAllTrips={handleDeleteAllTrips}
            onUpdateNotes={handleUpdateNotesInHistory}
            onBack={() => {
              setItinerary(null);
              setActivePage('planner');
            }}
          />
        )}
          </>
        )}
      </main>

      {/* Popup Message Modal when same location & criteria already selected */}
      <AlreadySelectedModal 
        isOpen={duplicateModal.isOpen}
        onClose={() => setDuplicateModal(prev => ({ ...prev, isOpen: false }))}
        onOpenSavedTrip={(trip) => {
          handleReloadTripFromHistory(trip);
          setDuplicateModal(prev => ({ ...prev, isOpen: false }));
        }}
        onProceedAnyway={duplicateModal.onProceedAnyway}
        existingTrip={duplicateModal.existingTrip}
        criteria={duplicateModal.criteria}
      />

      {/* Prompt User on Refresh: Want to save history or not (yes or no) */}
      <RefreshSavePromptModal 
        isOpen={refreshPromptModal.isOpen}
        trip={refreshPromptModal.trip}
        onYes={handleRefreshSelectYes}
        onNo={handleRefreshSelectNo}
        savedCount={savedTrips.length}
      />

      {/* ONE-BUTTON TRIP COPILOT DRAWER / MODAL */}
      {isCopilotOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/40 backdrop-blur-xs transition-opacity animate-in fade-in-50 duration-200">
          <div 
            className="fixed inset-0" 
            onClick={() => setIsCopilotOpen(false)} 
            aria-hidden="true" 
          />
          <div className="relative w-full max-w-md h-full bg-white shadow-2xl flex flex-col z-10 animate-in slide-in-from-right duration-300">
            <ChatPanel 
              itinerary={itinerary}
              onSendMessage={handleSendMessage}
              messages={chatMessages}
              isLoading={isChatLoading}
              onClose={() => setIsCopilotOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Floating One-Button Namaste AI Trigger on Left Corner */}
      {itinerary && activePage === 'planner' && !isCopilotOpen && (
        <button
          type="button"
          onClick={() => setIsCopilotOpen(true)}
          className="fixed bottom-6 left-6 z-40 bg-gradient-to-r from-amber-600 via-orange-600 to-rose-600 hover:from-amber-700 hover:to-rose-700 text-white font-extrabold text-xs px-5 py-3 rounded-full shadow-2xl flex items-center gap-2.5 transition-all hover:scale-105 cursor-pointer border-2 border-white/90 shadow-orange-500/30"
          title="Open Namaste AI"
        >
          <NamasteAvatar size={26} className="shadow-xs" />
          <span>Namaste AI</span>
          <span className="bg-white/30 text-[10px] px-2 py-0.5 rounded-full text-white font-black">AI</span>
        </button>
      )}

      {/* Save Success Toast */}
      {saveToast && (
        <div className="fixed bottom-6 right-6 z-50 bg-emerald-600 text-white font-extrabold text-xs px-4 py-3 rounded-2xl shadow-xl flex items-center gap-2 animate-bounce">
          <Check className="w-4 h-4" />
          <span>{saveToast}</span>
        </div>
      )}

      {/* Rich Patriotic & Multi-Modal Transit Footer */}
      <Footer onNavigatePage={handleNavigatePage} />
    </div>
  );
}
