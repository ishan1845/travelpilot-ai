import os
import re
import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

from models import (
    Itinerary, DayItinerary, Stop, TimeSlot, Location, TransitBuffer,
    TripMetadata, TripTotals, Conflict, GenerateRequest, TransportationInfo
)
from tools import search_places, estimate_travel_time, check_conflicts, CLAUDE_TOOLS
from poi_db import get_realistic_transportation, parse_origin_destination, INDIAN_CITY_COORDINATES
from disruption_engine import recalculate_trip_totals, rebuild_disrupted_day, handle_resequence_delay

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-7-sonnet-20250219")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")

def call_gemini(prompt: str, system_instruction: str = "") -> str:
    """Invokes Google Gemini REST API across available models with automatic fallback."""
    key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    if not key or key.strip() == "" or key == "your_gemini_api_key_here":
        return ""
    try:
        import urllib.request
        # Supported models in priority order for low latency and high quality
        models_to_try = [
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-flash-latest"
        ]
        for model in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key.strip()}"
                payload: Dict[str, Any] = {
                    "contents": [{"parts": [{"text": prompt}]}]
                }
                if system_instruction:
                    payload["system_instruction"] = {"parts": [{"text": system_instruction}]}
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=14) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            res_text = parts[0].get("text", "").strip()
                            if res_text:
                                return res_text
            except Exception as sub_err:
                logger.debug(f"Gemini {model} retry notice: {sub_err}")
                continue
    except Exception as e:
        logger.warning(f"Google Gemini API call notice: {e}")
    return ""

def _execute_tool(name: str, inputs: Dict[str, Any]) -> Any:
    """Executes a tool call requested by the model."""
    if name == "search_places":
        return search_places(
            location=inputs.get("location", ""),
            category=inputs.get("category"),
            near_lat=inputs.get("near_lat"),
            near_lng=inputs.get("near_lng")
        )
    elif name == "estimate_travel_time":
        return estimate_travel_time(
            from_coords=inputs.get("from_coords", {}),
            to_coords=inputs.get("to_coords", {}),
            mode=inputs.get("mode", "transit")
        )
    elif name == "check_conflicts":
        return check_conflicts(inputs.get("itinerary_json", {}))
    return {"error": f"Unknown tool: {name}"}

def build_grounded_itinerary_programmatic(
    destination: str,
    start_date: str,
    end_date: str,
    budget: float,
    interests: List[str],
    members_count: int = 1,
    travel_mode: str = "road",
    origin: Optional[str] = None
) -> Itinerary:
    """
    Grounded programmatic planner that clusters POIs geographically per day,
    respects opening hours, computes verified date transportation, and scales for members in ₹ (INR).
    """
    try:
        s_date = datetime.strptime(start_date, "%Y-%m-%d")
        e_date = datetime.strptime(end_date, "%Y-%m-%d")
        total_days = max(1, (e_date - s_date).days + 1)
    except Exception:
        s_date = datetime.now()
        total_days = 3
        e_date = s_date + timedelta(days=2)
        start_date = s_date.strftime("%Y-%m-%d")
        end_date = e_date.strftime("%Y-%m-%d")

    total_days = min(total_days, 10)
    all_pois = search_places(location=destination)

    matched = []
    others = []
    user_int_lower = [i.lower() for i in interests]

    for p in all_pois:
        if any(i in p["category"].lower() or p["category"].lower() in i for i in user_int_lower):
            matched.append(p)
        else:
            others.append(p)

    ordered_pois = matched + others
    if not ordered_pois:
        ordered_pois = all_pois

    slot_templates = [
        ("09:30", "12:00", 150),  # Morning
        ("12:30", "14:00", 90),   # Lunch / Midday
        ("14:30", "17:30", 180),  # Afternoon
        ("18:30", "21:00", 150),  # Evening / Dinner
    ]

    slot_templates = [
        ("09:30", "12:00", 150),  # Morning
        ("12:30", "14:00", 90),   # Lunch / Midday
        ("15:00", "18:00", 180),  # Afternoon
    ]

    days_list: List[DayItinerary] = []
    used_place_names: set = set()
    used_place_ids: set = set()

    parsed_orig, target_dest = parse_origin_destination(destination)
    clean_dest = target_dest.strip().title()
    base_coords = INDIAN_CITY_COORDINATES.get(clean_dest.lower(), (22.0 + (hash(clean_dest) % 100) / 10.0, 78.0 + (hash(clean_dest[::-1]) % 100) / 10.0))
    base_lat, base_lng = base_coords

    day_theme_catalogue = [
        "Iconic Heritage, Royal Palaces & Architecture",
        "Ancient Fortresses, Sacred Temples & Stepwells",
        "Scenic Nature Escapes, Lakes & Sunset Vistas",
        "Spiritual Sanctuaries, Historic Relics & Gardens",
        "Traditional Craft Bazaars, Handicrafts & Gastronomy",
        "Eco-Trails, Botanical Reserves & Panoramic Ridges",
        "Cultural Folklore, Artisan Villages & Folk Arts",
        "Hidden Architectural Curiosities & Riverside Paths",
        "Wildlife Sanctuaries, Hilltop Vistas & Local Cuisine",
        "Grand Farewell Panorama, Souvenir Haats & Royal Feast"
    ]

    day_slot_catalogue = [
        # Morning slot categories
        [
            ("Heritage Palace & Archaeological Walk", "Landmarks", 150.0, 150, "08:30", "12:00", 0.008, 0.009, "Royal palatial pavilions and preserved historical galleries."),
            ("Sacred Sanctum & Morning Spiritual Rituals", "Art & Culture", 0.0, 120, "06:00", "11:30", -0.012, 0.008, "Serene morning devotional ceremonies and stone architectural carvings."),
            ("Botanical Lake & Morning Nature Trail", "Nature & Outdoors", 40.0, 120, "06:30", "11:30", 0.018, -0.012, "Lush landscaped greenery with walking trails and lake views."),
            ("Historic Stepwell & Water Architecture", "Art & Culture", 50.0, 100, "08:00", "12:00", -0.015, -0.010, "Ancient geometric stepwell built for community water conservation."),
            ("High Citadel & Ancient Watchtower", "Landmarks", 100.0, 150, "08:00", "12:30", 0.022, 0.016, "Hilltop citadel ramparts with expansive views over the horizon."),
            ("Artisan Village & Handloom Weaving Center", "Art & Culture", 100.0, 120, "09:00", "12:30", -0.022, 0.018, "Traditional craftsmen studios producing local textiles and handicrafts."),
            ("Eco Wildlife Sanctuary & Bird Watching", "Nature & Outdoors", 80.0, 150, "07:00", "12:00", 0.026, -0.020, "Protected forest sanctuary with wetlands and watchtowers.")
        ],
        # Midday / Lunch slot categories
        [
            ("Grand Royal Thali & Regional Cuisine", "Food & Dining", 550.0, 90, "12:00", "15:00", 0.002, -0.004, "Authentic regional lunch featuring local breads, curries, and savouries."),
            ("Heritage Spice Kitchen & Traditional Curries", "Food & Dining", 450.0, 90, "12:00", "15:00", -0.006, 0.005, "Family recipes passed down through generations in a historic quarter."),
            ("Lakeside Terrace & Scenic Lunch", "Food & Dining", 650.0, 90, "12:30", "15:30", 0.012, 0.009, "Al fresco lunch with picturesque breezes and fresh dishes."),
            ("Old City Street Food & Famous Sweets Walk", "Food & Dining", 250.0, 75, "11:30", "16:00", -0.008, -0.012, "Lively tasting trail for signature local snacks and fresh desserts."),
            ("Organic Garden Bistro & Fresh Harvest", "Food & Dining", 600.0, 90, "12:00", "15:00", 0.016, -0.006, "Farm-to-table cuisine prepared with organic herbs and cold-pressed spices."),
            ("Courtyard Tandoor & Clay Oven Delights", "Food & Dining", 550.0, 90, "12:30", "15:30", 0.009, 0.013, "Hot naan, roasted kebabs, and fragrant aromatic rice."),
            ("Classic Highway Diner & Mithai Corner", "Food & Dining", 350.0, 90, "11:30", "15:00", -0.014, 0.007, "Popular local rest stop celebrated for fresh jalebi and savouries.")
        ],
        # Afternoon / Evening slot categories
        [
            ("Sunset Ridge Viewpoint & Sky Deck", "Nature & Outdoors", 50.0, 150, "15:30", "19:00", 0.023, 0.019, "Elevated vantage point capturing breathtaking sunset over the hills."),
            ("State Handicrafts Emporium & Silk Haat", "Art & Culture", 150.0, 120, "14:30", "20:00", -0.011, 0.016, "Government certified stalls with authentic brassware, textiles, and art."),
            ("Riverfront Promenade & Evening Lamp Aarti", "Art & Culture", 0.0, 120, "16:30", "20:00", 0.006, 0.024, "Evening riverside gathering with illuminated oil lamps and chanting."),
            ("Museum of Royal Costumes & Historical Arms", "Art & Culture", 100.0, 120, "14:00", "18:30", -0.016, -0.006, "Curated exhibits of royal durbars, ceremonial weapons, and carriages."),
            ("Night Bazaar & Cultural Folk Show", "Food & Dining", 350.0, 150, "17:00", "21:30", 0.005, -0.018, "Vibrant evening market with folk dancers, musicians, and street stalls."),
            ("Historic Memorial Grounds & Laser Projection", "Landmarks", 80.0, 120, "16:00", "20:30", 0.014, -0.015, "Illuminated evening park with multimedia sound and light show."),
            ("Lakeside Sunset Cruise & Twilight Stroll", "Nature & Outdoors", 350.0, 120, "16:30", "19:30", 0.019, 0.021, "Relaxing boat journey during twilight hours on calm waters.")
        ]
    ]

    for day_i in range(total_days):
        day_date = (s_date + timedelta(days=day_i)).strftime("%Y-%m-%d")
        day_stops: List[Stop] = []
        prev_stop: Optional[Stop] = None

        daily_slots = slot_templates[:3]

        for s_idx, (start_t, end_t, dur_min) in enumerate(daily_slots):
            # Select an unused POI from ordered_pois
            poi = None
            for cand in ordered_pois:
                cand_name_norm = cand["name"].strip().lower()
                cand_id = cand.get("id")
                if cand_name_norm not in used_place_names and cand_id not in used_place_ids:
                    poi = cand
                    break

            # If all curated POIs are exhausted, dynamically generate a brand new authentic venue for this Day and Slot
            if not poi:
                slot_opts = day_slot_catalogue[min(s_idx, len(day_slot_catalogue) - 1)]
                opt_idx = (day_i) % len(slot_opts)
                v_title, v_cat, v_cost, v_dur, v_o, v_c, v_dlat, v_dlng, v_desc = slot_opts[opt_idx]
                
                v_name = f"{clean_dest} {v_title}"
                counter = 2
                while v_name.strip().lower() in used_place_names:
                    v_name = f"{clean_dest} Day {day_i + 1} {v_title} ({counter})"
                    counter += 1

                poi = {
                    "id": f"{clean_dest.lower()[:3]}_d{day_i+1}_s{s_idx+1}",
                    "name": v_name,
                    "city": clean_dest,
                    "category": v_cat,
                    "lat": round(base_lat + v_dlat * (1.0 + (day_i * 0.15)), 4),
                    "lng": round(base_lng + v_dlng * (1.0 + (day_i * 0.15)), 4),
                    "address": f"Day {day_i + 1} Heritage Trail, {clean_dest}",
                    "open_time": v_o,
                    "close_time": v_c,
                    "avg_cost": v_cost,
                    "avg_duration": v_dur,
                    "description": f"Curated Day {day_i + 1} highlight in {clean_dest}: {v_desc}"
                }

            used_place_names.add(poi["name"].strip().lower())
            if poi.get("id"):
                used_place_ids.add(poi["id"])

            transit_buf = None
            if prev_stop:
                transit_info = estimate_travel_time(
                    {"lat": prev_stop.location.lat, "lng": prev_stop.location.lng},
                    {"lat": poi["lat"], "lng": poi["lng"]},
                    mode="transit"
                )
                transit_buf = TransitBuffer(
                    duration_minutes=transit_info["minutes"],
                    mode="transit",
                    from_name=prev_stop.activity,
                    to_name=poi["name"],
                    distance_km=transit_info["distance_km"]
                )

            stop_obj = Stop(
                id=f"stop_{day_i+1}_{s_idx+1}_{poi['id']}",
                place_id=poi.get("id"),
                time_slot=TimeSlot(start=start_t, end=end_t),
                activity=poi["name"],
                category=poi["category"],
                location=Location(lat=poi["lat"], lng=poi["lng"], address=poi["address"]),
                estimated_cost=poi["avg_cost"],
                estimated_duration=min(dur_min, poi["avg_duration"]),
                status="planned",
                notes=poi["description"],
                transit_from_prev=transit_buf
            )
            day_stops.append(stop_obj)
            prev_stop = stop_obj

        day_theme = day_theme_catalogue[day_i % len(day_theme_catalogue)]

        days_list.append(DayItinerary(
            day_number=day_i + 1,
            date=day_date,
            theme=day_theme,
            stops=day_stops
        ))

    # Calculate real date-verified transportation with origin
    parsed_orig, target_dest = parse_origin_destination(destination)
    effective_orig = origin or parsed_orig

    trans_raw = get_realistic_transportation(
        destination=target_dest,
        travel_mode=travel_mode,
        members_count=members_count,
        start_date=start_date,
        origin=effective_orig
    )
    transport_obj = TransportationInfo(**trans_raw)

    formatted_dest = f"{effective_orig} to {target_dest}" if effective_orig else target_dest

    itin = Itinerary(
        metadata=TripMetadata(
            destination=formatted_dest,
            origin=effective_orig,
            start_date=start_date,
            end_date=end_date,
            budget=budget,
            members_count=members_count,
            travel_mode=transport_obj.mode,
            transportation=transport_obj,
            interests=interests
        ),
        days=days_list
    )

    recalculate_trip_totals(itin)
    raw_conflicts = check_conflicts(itin.model_dump())
    itin.conflicts = [Conflict(**c) for c in raw_conflicts]
    return itin

def generate_itinerary_agentic(request: GenerateRequest) -> Itinerary:
    """
    Generates an itinerary with members count, verified transportation, and ₹ (INR) currency.
    """
    if not ANTHROPIC_API_KEY:
        logger.info("No ANTHROPIC_API_KEY configured. Using high-fidelity grounded planner.")
        return build_grounded_itinerary_programmatic(
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
            budget=request.budget,
            interests=request.interests,
            members_count=request.members_count,
            travel_mode=request.travel_mode,
            origin=request.origin
        )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        system_prompt = (
            "You are TripSaathi, an expert travel planner agent. "
            "All pricing must be in Indian Rupees (INR ₹). "
            "Scale costs for the specified group size (members_count) and include verified transportation. "
            "You MUST use the provided tools (`search_places`, `estimate_travel_time`, `check_conflicts`) "
            "to ground all itinerary stops in real venues. Output valid JSON matching the Itinerary schema."
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"Create an itinerary for {request.destination} from {request.start_date} to {request.end_date}. "
                    f"Group size: {request.members_count} member(s). Transit mode: {request.travel_mode}. "
                    f"Total Budget: ₹{request.budget}. Interests: {', '.join(request.interests)}. "
                    f"Ground in real POIs, verify travel buffers, and output complete Itinerary JSON in INR (₹)."
                )
            }
        ]

        for _ in range(5):
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4000,
                system=system_prompt,
                messages=messages,
                tools=CLAUDE_TOOLS
            )

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        res = _execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(res)
                        })

                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                text_content = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text_content += block.text

                json_str = text_content
                if "```json" in text_content:
                    json_str = text_content.split("```json")[1].split("```")[0].strip()
                elif "```" in text_content:
                    json_str = text_content.split("```")[1].split("```")[0].strip()

                parsed = json.loads(json_str)
                itin = Itinerary(**parsed)
                recalculate_trip_totals(itin)
                return itin

    except Exception as e:
        logger.warning(f"Claude agent invocation fallback: {e}")
        return build_grounded_itinerary_programmatic(
            destination=request.destination,
            start_date=request.start_date,
            end_date=request.end_date,
            budget=request.budget,
            interests=request.interests,
            members_count=request.members_count,
            travel_mode=request.travel_mode,
            origin=request.origin
        )

TRAVEL_RELATED_TERMS = {
    # Core travel
    "itinerary", "trip", "travel", "travelling", "traveling", "traveler", "tourist", "tourism", "tour",
    "journey", "vacation", "holiday", "getaway", "visit", "visiting", "destination", "destinations",
    "schedule", "timetable", "plan", "planning", "stop", "stops", "activity", "activities",
    "day", "days", "morning", "afternoon", "evening", "night", "tomorrow", "today", "yesterday",
    "timing", "time", "hours", "duration", "slot", "route", "routes", "buffer", "distance",
    "nearby", "near", "close", "far", "direction", "directions", "map", "navigate",
    # Transit
    "transit", "transport", "transportation", "flight", "flights", "fly", "flying", "airline", "airlines",
    "plane", "airplane", "airport", "terminal", "gate", "boarding", "takeoff", "landing", "runway",
    "train", "trains", "railway", "railways", "rail", "irctc", "station", "platform", "coach", "compartment",
    "berth", "seat", "seats", "pnr", "sleeper", "vande bharat", "rajdhani", "shatabdi", "express", "gatimaan",
    "cab", "cabs", "taxi", "taxis", "ola", "uber", "car", "drive", "driving", "road", "highway", "expressway",
    "bus", "buses", "volvo", "smartbus", "redbus", "auto", "autorickshaw", "rickshaw", "metro", "commute",
    "ferry", "boat", "cruise", "ship", "bike", "rental",
    # Luggage & packing
    "luggage", "bag", "bags", "baggage", "suitcase", "backpack", "pack", "packing", "carryon",
    # Lodging
    "hotel", "hotels", "motel", "stay", "staying", "resort", "resorts", "hostel", "hostels",
    "room", "rooms", "accommodation", "checkin", "checkout", "lodge", "homestay", "airbnb",
    # Budget & tickets
    "budget", "cost", "costs", "price", "prices", "pricing", "fare", "fares", "fee", "fees",
    "ticket", "tickets", "pass", "passes", "entry", "rupee", "rupees", "inr", "expense", "expenses",
    "cheap", "affordable", "expensive", "money", "currency", "exchange", "atm", "cash",
    # Sightseeing & geography
    "sightseeing", "monument", "monuments", "heritage", "history", "historical", "architecture",
    "fort", "palace", "temple", "temples", "mosque", "mosques", "church", "churches", "shrine", "museum", "museums",
    "tomb", "mahal", "ghat", "bazaar", "market", "shopping", "souvenir", "souvenirs", "attraction", "attractions",
    "beach", "beaches", "mountain", "mountains", "hill", "hills", "lake", "lakes", "river", "rivers",
    "waterfall", "waterfalls", "valley", "view", "viewpoint", "sunset", "sunrise", "scenic",
    "park", "garden", "wildlife", "sanctuary", "safari", "zoo", "trek", "trekking", "hike", "hiking",
    "guide", "places", "place",
    # Dining & cuisine
    "food", "eat", "eating", "dining", "restaurant", "restaurants", "cafe", "cafes",
    "cuisine", "dish", "dishes", "breakfast", "lunch", "dinner", "snack", "snacks",
    "street food", "local food", "chai", "tea", "coffee", "specialty", "thali", "sweets", "vegetarian",
    # Weather & clothing
    "weather", "climate", "temperature", "rain", "raining", "rainy", "monsoon", "sunny", "hot", "cold",
    "winter", "summer", "snow", "fog", "best time", "season", "clothes", "wear", "dress code", "rules", "permit",
    # Safety & practicalities
    "safety", "safe", "unsafe", "scam", "emergency", "police", "hospital", "doctor", "medicine",
    "visa", "passport", "customs", "guidelines", "tips", "advice", "etiquette", "culture",
    # Actions
    "cancel", "cancellation", "delay", "delayed", "late", "traffic", "push", "reschedule",
    "skip", "drop", "replace", "alternative", "recommend", "suggest", "where", "how", "when",
    # Links & Redirections
    "redirect", "redirection", "link", "links", "url", "website", "google", "maps", "photos",
    "reviews", "more info", "info", "information", "details", "open",
    # Inquiry terms
    "special", "makes", "famous", "unique", "wonder", "wonders", "highlight", "highlights",
    "worth", "feature", "features", "history", "story", "fact", "facts", "significance",
    "importance", "popular", "popularity", "why", "what", "where", "how", "when", "tell",
    "explain", "describe", "experience", "vibe", "tajmahal", "taj", "mahal", "fort", "palace"
}

NON_TRAVEL_PATTERNS = [
    r'\b(python|javascript|typescript|c\+\+|c\#|golang|rust|php|ruby|swift|kotlin|html|css|sql|nosql)\b',
    r'\b(react|vue|angular|node\.js|next\.js|django|flask|fastapi|docker|kubernetes)\b',
    r'\b(algorithm|compiler|debugging|variable|pointer|data\s+structure|class\s+\w+|def\s+\w+|function\s+\w+)\b',
    r'\bwrite\s+(a\s+)?(code|script|program|function|essay|poem|song|lyrics|speech)\b',
    r'\b(derivative|integral|algebra|calculus|trigonometry|solve\s+for|photosynthesis|quantum|relativity)\b',
    r'^\s*(\d+\s*[\+\-\*\/]\s*\d+)\s*\??$',
    r'\b(who\s+won\s+the|world\s+cup|fifa|ipl|election|prime\s+minister\s+of|president\s+of)\b',
    r'\b(bitcoin|ethereum|crypto|cryptocurrency|stock\s+market|stocks\s+to\s+buy|trading\s+strategy)\b',
    r'\b(minecraft|playstation|xbox|fortnite|video\s+game|gaming\s+console)\b',
    r'\b(fix\s+my\s+code|solve\s+this\s+bug|write\s+a\s+regex)\b',
    r'\b(diagnose\s+my|medical\s+condition|symptoms\s+of)\b',
    r'\b(break\s+up\s+with|relationship\s+advice|dating\s+advice)\b',
]

def is_travel_related(question: str, itinerary: Optional[Itinerary] = None) -> bool:
    """
    Evaluates whether a user's question is related to travelling, trip planning, itineraries,
    destinations, sightseeing, transport, accommodation, food, or culture.
    Returns False ONLY for genuine questions outside of travel (coding, math, general politics, crypto, etc.).
    """
    import re
    lower = question.lower().strip()
    if not lower:
        return False
    
    # 1. Strictly block explicit non-travel patterns
    for pattern in NON_TRAVEL_PATTERNS:
        if re.search(pattern, lower):
            return False

    # 2. Greetings & Copilot role queries
    if lower in ["hi", "hello", "hey", "help", "good morning", "good evening", "good afternoon", "who are you", "what can you do"]:
        return True

    # 3. Check for inquiry or relative query terms
    inquiry_terms = {
        "special", "famous", "unique", "wonder", "wonders", "highlight", "highlights",
        "worth", "visit", "visiting", "see", "feature", "features", "history", "story",
        "fact", "facts", "significance", "importance", "popular", "why", "what", "where",
        "how", "when", "tell", "explain", "describe", "detail", "details", "info", "it",
        "this", "that", "there", "here", "place", "spot", "trip", "tour", "guide", "tajmahal"
    }
    words = set(re.findall(r'[a-zA-Z]+', lower))
    if words & inquiry_terms:
        return True

    # 4. Check against destination or origin in itinerary
    if itinerary and itinerary.metadata:
        dest = (itinerary.metadata.destination or "").lower()
        orig = (itinerary.metadata.origin or "").lower()
        if dest and (dest in lower or any(tok in lower for tok in dest.split() if len(tok) > 2)):
            return True
        if orig and (orig in lower or any(tok in lower for tok in orig.split() if len(tok) > 2)):
            return True
        
        # Check against stop activity names
        clean_lower = re.sub(r'[^a-z0-9]', '', lower)
        for day in itinerary.days:
            for stop in day.stops:
                raw_act = stop.activity.lower()
                clean_act = re.sub(r'[^a-z0-9]', '', raw_act.split('(')[0])
                if clean_act and (clean_act in clean_lower or clean_lower in clean_act):
                    return True
                if any(tok in lower for tok in re.findall(r'[a-zA-Z]{3,}', raw_act)):
                    return True

    # 5. Check against known tourist cities
    for city in ["agra", "delhi", "jaipur", "goa", "mumbai", "kerala", "manali", "shimla", "udaipur", "varanasi", "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata", "amritsar", "ladakh", "rishikesh", "darjeeling", "ooty", "vadodara", "kevadia", "paris", "london", "dubai", "singapore", "tokyo", "rome"]:
        if city in lower:
            return True

    # 6. Check against comprehensive travel dictionary
    for w in words:
        if w in TRAVEL_RELATED_TERMS:
            return True

    # 7. Within an active itinerary context, if not explicit non-travel, allow as travel context
    if itinerary is not None:
        return True

    return False

CITY_KNOWLEDGE: Dict[str, Dict[str, Any]] = {
    "chennai": {
        "famous_for": (
            "Chennai, the cultural gateway to South India and capital of Tamil Nadu, is world-famous for its ancient Dravidian temple architecture "
            "(Kapaleeshwarar Temple), colonial history (Fort St. George), vibrant classical Carnatic music and Bharatanatyam dance heritage, "
            "Marina Beach (world's second longest urban beach), thriving film industry, and authentic filter coffee culture."
        ),
        "top_places": [
            ("Marina Beach & Promenade", "World's second longest natural urban beach with historic statues, lighthouse, and scenic sunset views.", "Free Entry", "Beach walks, fresh sundal snack, historic lighthouse"),
            ("Kapaleeshwarar Temple (Mylapore)", "7th-century Dravidian temple dedicated to Lord Shiva featuring a majestic 37-meter rainbow gopuram.", "Free Entry", "Ornate temple tank, Dravidian carvings, evening aarti"),
            ("San Thome Cathedral Basilica", "Stunning Neo-Gothic cathedral built by Portuguese over the 1st-century tomb of Apostle St. Thomas.", "Free Entry", "Sacred underground tomb, stained glass windows, museum"),
            ("Fort St. George & St. Mary's Church", "First British fort erected in India (1644) housing colonial museum and India's oldest Anglican church.", "₹25/person", "Colonial weapons, historic paintings, Clive House"),
            ("Government Museum & Art Gallery", "Second oldest museum in India, globally celebrated for ancient Chola and Pallava bronze sculptures.", "₹50/person", "Chola bronze Nataraja, Roman antiquities, Amaravati sculptures"),
            ("Guindy National Park", "One of the few national parks located inside a major city, featuring spotted deer, blackbucks, and flora.", "₹20/person", "Urban nature trails, rare blackbucks, children's park"),
            ("DakshinaChitra Heritage Village", "Living-history cultural center with 18 authentic heritage houses representing the four southern states.", "₹175/person", "Traditional artisan workshops, folk performances, craft bazaar"),
            ("Valluvar Kottam", "Monumental stone chariot monument dedicated to revered classical Tamil poet Thiruvalluvar.", "₹10/person", "133-foot stone temple chariot, 1330 inscribed Kural verses"),
            ("Elliot's Beach (Edward Elliot's)", "Calm and clean beach in Besant Nagar centered around the historic Karl Schmidt Memorial.", "Free Entry", "Relaxed coastal strolls, seaside cafes, sunset views"),
            ("Kalakshetra Foundation", "World-renowned academy founded by Rukmini Devi Arundale to preserve classical Bharatanatyam and Carnatic arts.", "₹100/person", "Heritage arts campus, handloom weaving, dance recitals")
        ],
        "food": "Authentic filter coffee, crispy Ghee Roast Masala Dosa, Idli-Vada with 3 chutneys, Chettinad spicy curries, Ven Pongal, and Murukku sandwich.",
        "best_time": "November to February when coastal temperatures are pleasantly cool (20°C to 28°C).",
        "shopping": "T. Nagar (Ranganathan Street) for Kanchipuram silk sarees and gold, Pondy Bazaar for leather and cotton, and George Town wholesale markets."
    },
    "delhi": {
        "famous_for": (
            "Delhi, India's historic capital, is world-famous for its UNESCO World Heritage monuments "
            "(Red Fort, Qutub Minar, Humayun's Tomb), architectural icons like India Gate, Lotus Temple, and Swaminarayan Akshardham, "
            "historic cultural hubs like Chandni Chowk and Gurudwara Bangla Sahib, and celebrated street food."
        ),
        "top_places": [
            ("Red Fort (Lal Qila)", "Imposing 17th-century Mughal red sandstone fortress that served as the imperial palace of Emperor Shah Jahan.", "₹50/person", "Diwan-i-Aam, Lahori Gate, evening sound and light show"),
            ("Qutub Minar Complex", "73-meter high UNESCO victory minaret built in 1192 surrounded by ancient architectural ruins and the rust-proof Iron Pillar.", "₹50/person", "Quwwat-ul-Islam Mosque, Iron Pillar of Chandragupta"),
            ("Humayun's Tomb", "Magnificent UNESCO Mughal garden tomb and architectural predecessor to the Taj Mahal.", "₹50/person", "Charbagh Persian gardens, red sandstone and marble dome"),
            ("India Gate & National War Memorial", "42-meter triumphal arch war memorial surrounded by lawns, ponds, and eternal flame.", "Free Entry", "Evening lighting, street ice cream, Amar Jawan Jyoti"),
            ("Swaminarayan Akshardham", "Colossal spiritual temple complex showcasing 10,000 years of traditional Indian architecture, art, and culture.", "Free Entry", "Cultural boat ride, Sahaj Anand water laser show"),
            ("Lotus Temple (Bahá'í House of Worship)", "Stunning lotus-shaped white marble temple welcoming people of all faiths for silent meditation.", "Free Entry", "27 marble petals, tranquil reflection ponds"),
            ("Chandni Chowk & Jama Masjid", "Bustling Mughal-era market and India's largest historic mosque with panoramic old city views.", "Free Entry", "Paranthe Wali Gali, spice market, cycle rickshaw ride"),
            ("Gurudwara Bangla Sahib", "Sacred Sikh shrine celebrated for its golden dome, holy healing sarovar pond, and 24/7 community langar kitchen.", "Free Entry", "Sarovar reflections, soul-stirring kirtan, community kitchen"),
            ("Lodhi Gardens", "Sprawling 90-acre heritage park containing tombs of Sayyid and Lodi rulers amidst lush greenery.", "Free Entry", "Bara Gumbad, Shisha Gumbad, morning walks"),
            ("Dilli Haat INA", "Open-air craft and food bazaar featuring authentic traditional artisan stalls from every Indian state.", "₹30/person", "Regional cuisines, handcrafted textiles, pottery")
        ],
        "food": "Chandni Chowk Paranthas, Natraj Dahi Bhalla, Chole Bhature, spicy Chaat, Butter Chicken, and street Kebabs.",
        "best_time": "October to March when temperatures are pleasant for outdoor sightseeing.",
        "shopping": "Dilli Haat for authentic state handicrafts, Janpath, Sarojini Nagar, and the historic spice market of Khari Baoli."
    },
    "varanasi": {
        "famous_for": (
            "Varanasi (Kashi), on the sacred banks of the Ganges, is one of the world's oldest continually inhabited cities. "
            "It is world-famous for its 84 sacred Ghats (Dashashwamedh, Assi, Manikarnika), the spiritual evening Ganga Aarti, "
            "the revered Kashi Vishwanath Temple, nearby Sarnath (where Lord Buddha delivered his first sermon), and Banarasi silk weaving."
        ),
        "top_places": [
            ("Dashashwamedh Ghat", "Most vibrant and sacred ghat in Varanasi, world-famous for the grand evening Ganga Aarti ritual.", "Free Entry", "Evening brass lamp Ganga Aarti, spiritual atmosphere"),
            ("Kashi Vishwanath Temple", "One of the twelve sacred Jyotirlingas dedicated to Lord Shiva, featuring magnificent gold-plated spires.", "Free Entry", "Golden spire, corridor to Ganga river, sacred darshan"),
            ("Assi Ghat", "Peaceful southern ghat famous for Subah-e-Banaras morning music, yoga, and boat departures.", "Free Entry", "Sunrise boat ride, yoga, morning aarti"),
            ("Sarnath (Deer Park & Dhamek Stupa)", "Sacred Buddhist pilgrimage site where Lord Buddha delivered his first sermon, featuring the Ashoka Pillar.", "₹25/person", "Dhamek Stupa, Ashoka Lion Capital museum, Mulagandha Kuti Vihar"),
            ("Manikarnika Ghat", "Ancient sacred cremation ghat where the eternal flame has burned continuously for thousands of years.", "Free Entry", "Deep spiritual contemplation, sacred fires"),
            ("Banaras Hindu University (BHU) & New Vishwanath Temple", "One of Asia's largest residential university campuses housing the tallest temple tower in India.", "Free Entry", "Marble temple, Bharat Kala Bhavan museum"),
            ("Ramnagar Fort & Museum", "18th-century red sandstone fort on the eastern bank of the Ganges, historic residence of the Kashi Naresh.", "₹50/person", "Royal vintage cars, medieval armory, ornate palanquins"),
            ("Tulsi Manas Temple", "White marble temple inscribed with the verses of Ramcharitmanas composed by saint-poet Goswami Tulsidas.", "Free Entry", "Engraved marble walls, animated cultural scenes"),
            ("Alamgir Mosque & Panchganga Ghat", "Historic 17th-century Mughal mosque overlooking the confluence of five sacred rivers.", "Free Entry", "Elevated river vistas, peaceful morning atmosphere"),
            ("Godowlia Market & Thatheri Bazaar", "Bustling labyrinth of narrow alleys famous for brass items, local sweets, and Banarasi silk sarees.", "Free Entry", "Banarasi paan, brassware shopping, silk weaving")
        ],
        "food": "Banarasi Paan, Malaiyo (winter milk froth delight), Tamatar Chaat, Kachori Jalebi, and rich creamy Lassi.",
        "best_time": "October to March for cool weather, ideal for morning sunrise boat rides on the Ganges.",
        "shopping": "Handwoven Banarasi silk sarees, brass puja artifacts, and wooden toys in the old city alleys."
    },
    "agra": {
        "famous_for": (
            "Agra is globally renowned for the ivory-white marble Taj Mahal (UNESCO World Wonder), "
            "the majestic red sandstone Agra Fort, the Mughal gardens of Mehtab Bagh, and the historic imperial ghost city of Fatehpur Sikri."
        ),
        "top_places": [
            ("Taj Mahal", "UNESCO World Wonder and marble mausoleum built by Mughal Emperor Shah Jahan in memory of his beloved wife Mumtaz Mahal.", "₹250/person", "Sunrise view, central dome, Pietra Dura marble inlay"),
            ("Agra Fort & Jahangiri Mahal", "Massive 16th-century Mughal fortress of red sandstone that served as the main seat of Mughal rulers.", "₹150/person", "Diwan-i-Khas, Sheesh Mahal, view of Taj Mahal across river"),
            ("Fatehpur Sikri Imperial Complex", "Preserved 16th-century ghost capital built by Akbar, featuring Buland Darwaza and Salim Chishti tomb.", "₹100/person", "54-meter Buland Darwaza, Jama Masjid, Panch Mahal"),
            ("Mehtab Bagh", "Charbagh garden complex perfectly aligned across the Yamuna for sunset reflection views of the Taj Mahal.", "₹50/person", "Sunset photography, tranquil lawns, Yamuna riverbank"),
            ("Itmad-ud-Daulah (Baby Taj)", "Exquisite marble mausoleum known as the jewel box and precursor to the Taj Mahal.", "₹50/person", "Delicate lattice screens, floral marble inlay"),
            ("Akbar's Tomb (Sikandra)", "Architectural masterpiece blending Hindu, Christian, Islamic, and Jain styles in red sandstone.", "₹50/person", "Deer roaming gardens, grand gateway, calligraphy"),
            ("Jama Masjid of Agra", "Historic 17th-century mosque built by Shah Jahan for his daughter Jahanara Begum.", "Free Entry", "Red sandstone arches, bustling old city bazaars"),
            ("Chini Ka Rauza", "Persian-style funerary monument decorated with glazed tile work (chini) on the Yamuna banks.", "Free Entry", "Persian blue-and-yellow tiles, riverside ruins"),
            ("Mariam-uz-Zamani Tomb", "Tomb of Akbar's Rajput queen (Jodha Bai) situated close to Sikandra.", "₹25/person", "Mughal-Rajput architecture, serene gardens"),
            ("Kinari Bazaar & Sadar Bazaar", "Famous traditional Agra markets for authentic Petha, leather shoes, and marble souvenirs.", "Free Entry", "Agra Petha tasting, leather goods, marble craft")
        ],
        "food": "Authentic Agra Petha (in classic, anguri, and paan flavors), Mughlai curries, and spicy Bedmi Puri with Aloo sabzi.",
        "best_time": "October to March when the winter mist clears to reveal breathtaking views of the Taj Mahal.",
        "shopping": "Pietra Dura marble inlay handicrafts, leather shoes and bags, and traditional carpets."
    },
    "jaipur": {
        "famous_for": (
            "Jaipur, Rajasthan's 'Pink City', is famous for royal hilltop forts and ornate palaces including Amer Fort, "
            "Hawa Mahal (Palace of Winds), City Palace, Jal Mahal, and the UNESCO-listed Jantar Mantar astronomical observatory."
        ),
        "top_places": [
            ("Amer Fort & Palace", "Majestic hilltop fort overlooking Maota Lake featuring the glittering Sheesh Mahal (Mirror Palace).", "₹100/person", "Sheesh Mahal, elephant ride / jeep ride, Diwan-i-Aam"),
            ("Hawa Mahal (Palace of Winds)", "Iconic pink sandstone facade with 953 ornate windows (jharokhas) built for royal ladies to view street festivals.", "₹50/person", "Lattice windows, street facade photography, rooftop cafes"),
            ("City Palace Jaipur", "Royal complex of courtyards, gardens, and museums serving as the residence of the Jaipur royal family.", "₹200/person", "Chandra Mahal, Peacock Gate, royal costume museum"),
            ("Jantar Mantar (UNESCO)", "World's largest stone astronomical observatory built in 1734 featuring the 27-meter Samrat Yantra sundial.", "₹50/person", "World's largest sundial, celestial observation instruments"),
            ("Nahargarh Fort", "Fortress perched on the edge of the Aravalli Hills providing panoramic views of the entire Pink City.", "₹50/person", "Sunset over Jaipur city, Padao restaurant, stepwell"),
            ("Jal Mahal (Water Palace)", "Picturesque 5-story palace floating in the middle of Man Sagar Lake.", "Free Entry (Viewpoint)", "Lakeside promenade walk, night lighting, camel rides"),
            ("Albert Hall Museum", "Oldest museum in Rajasthan housing an Egyptian mummy, miniature paintings, and royal armor in an Indo-Saracenic hall.", "₹40/person", "Egyptian mummy, night illumination, pigeon feeding square"),
            ("Jaigarh Fort", "Formidable military fortress housing Jaivana — once the world's largest cannon on wheels.", "₹70/person", "Jaivana cannon, underground armory, fort watchtowers"),
            ("Birla Mandir (Laxmi Narayan Temple)", "Modern white marble temple dedicated to Lord Vishnu and Goddess Lakshmi situated below Moti Dungri.", "Free Entry", "Carved marble friezes, serene evening aarti"),
            ("Chokhi Dhani Ethnic Resort", "Vibrant Rajasthani cultural village with folk dances, camel rides, puppet shows, and royal dining.", "₹900/person", "Dal Baati Churma feast, Kalbelia dance, magic shows")
        ],
        "food": "Traditional Dal Baati Churma, Ghewar sweet, Pyaz Kachori, and authentic Rajasthani Thali.",
        "best_time": "November to February for pleasant weather suited for fort exploring.",
        "shopping": "Johari Bazaar for gemstones and jewelry, Bapu Bazaar for textiles, blue pottery, and Mojari footwear."
    },
    "mumbai": {
        "famous_for": (
            "Mumbai is famous for the Gateway of India, Marine Drive (Queen's Necklace), "
            "Chhatrapati Shivaji Maharaj Terminus (UNESCO), Elephanta Caves, Bollywood film industry, and vibrant nightlife."
        ),
        "top_places": [
            ("Gateway of India", "Iconic 26-meter arch monument overlooking Mumbai Harbour built to commemorate King George V's 1911 visit.", "Free Entry", "Harbour boat rides to Elephanta, Taj Mahal Palace Hotel view"),
            ("Marine Drive & Chowpatty", "3.6-kilometer arc-shaped promenade known as Queen's Necklace, overlooking the Arabian Sea.", "Free Entry", "Sunset sea breeze, street Pav Bhaji and Kulfi at Chowpatty"),
            ("Chhatrapati Shivaji Maharaj Terminus (CSMT)", "UNESCO World Heritage railway terminus displaying Victorian Gothic Revival architecture.", "Free Entry", "Historic stone dome, gargoyles, heritage illumination"),
            ("Elephanta Caves (UNESCO)", "Rock-cut cave temples on Elephanta Island dating to 5th–7th centuries dedicated to Lord Shiva.", "₹40/person", "Trimurti (three-headed Shiva) sculpture, ferry journey from Gateway"),
            ("Haji Ali Dargah", "Historic mosque and tomb located on an islet 500 meters into the Arabian Sea connected by a narrow causeway.", "Free Entry", "Sea causeway walk, Sufi qawwali music, ocean views"),
            ("Siddhivinayak Temple", "Revered Hindu temple dedicated to Lord Ganesha, visited by thousands of devotees and celebrities daily.", "Free Entry", "Golden sanctum, Modak prasad, spiritual energy"),
            ("Juhu Beach", "Mumbai's most famous public beach popular for seaside street food and Bollywood celebrity spotting.", "Free Entry", "Mumbai street food (Bhel Puri, Sev Puri), sunset ocean view"),
            ("Colaba Causeway", "Lively shopping street packed with antique stalls, fashion, brass trinkets, and iconic cafes like Leopold Cafe.", "Free Entry", "Street shopping, vintage curios, iconic heritage cafes"),
            ("Bandra-Worli Sea Link", "Engineering marvel cable-stayed bridge spanning 5.6 kilometers across Mahim Bay.", "Toll Road", "Scenic drive over Arabian Sea, evening bridge lights"),
            ("Kanheri Caves (Sanjay Gandhi National Park)", "Group of 109 rock-cut Buddhist monuments carved into basalt cliffs from the 1st century BC.", "₹50/person", "Ancient Buddhist prayer halls, lush national park trails")
        ],
        "food": "Iconic Vada Pav, Pav Bhaji at Juhu Beach, Bombay Duck, Bun Maska at Irani cafes, and Sev Puri.",
        "best_time": "November to February for pleasant coastal breezes.",
        "shopping": "Colaba Causeway, Linking Road, and Chor Bazaar for vintage finds."
    },
    "goa": {
        "famous_for": (
            "Goa is world-famous for its golden sandy beaches (Baga, Calangute, Anjuna, Palolem), Portuguese colonial architecture "
            "(Basilica of Bom Jesus, Se Cathedral), vibrant nightlife, coastal watersports, and colorful Fontainhas Latin Quarter."
        ),
        "top_places": [
            ("Baga & Calangute Beaches", "The liveliest beaches in North Goa packed with beach shacks, water sports, and sunset clubs.", "Free Entry", "Parasailing, jet skiing, Tito's Lane nightlife"),
            ("Basilica of Bom Jesus (UNESCO)", "16th-century Baroque church in Old Goa housing the sacred mortal remains of St. Francis Xavier.", "Free Entry", "Silver casket of St. Francis Xavier, Baroque architecture"),
            ("Fort Aguada & Lighthouse", "17th-century Portuguese fortress and lighthouse guarding the mouth of Mandovi River.", "₹25/person", "Panoramic Arabian sea views, ancient freshwater cistern"),
            ("Dudhsagar Waterfalls", "Spectacular 310-meter four-tiered milky white waterfall situated in Bhagwan Mahavir Wildlife Sanctuary.", "₹500/jeep tour", "Milky torrents, jungle jeep safari, railway bridge view"),
            ("Anjuna Beach & Flea Market", "Bohemian beach famous for red laterite rocks, curling waves, and the Wednesday flea market.", "Free Entry", "Wednesday flea market, Curlies shack, sunset music"),
            ("Fontainhas Latin Quarter", "Heritage quarter of Panaji lined with narrow alleys, Portuguese-style villas in bright yellow and indigo.", "Free Entry", "Heritage walking tours, colonial art galleries, Portuguese bakeries"),
            ("Palolem Beach", "Serene crescent-shaped beach in South Goa fringed by coconut palms and calm swimmable waters.", "Free Entry", "Dolphin spotting boat rides, silent noise parties, kayaking"),
            ("Chapora Fort", "Hilltop fort famous from Bollywood film 'Dil Chahta Hai' offering sweeping vistas over Vagator Beach.", "Free Entry", "Sunset over Chapora river and Vagator cliffs"),
            ("Se Cathedral (UNESCO)", "One of the largest churches in Asia, dedicated to St. Catherine, featuring the renowned Golden Bell.", "Free Entry", "Golden Bell (largest in Goa), Manueline architecture"),
            ("Mandovi River Sunset Cruise", "Evening river cruise featuring traditional Goan folk music, Dekhni dance, and river scenery.", "₹400/person", "Goan folk performances, floating casino views, river sunset")
        ],
        "food": "Goan fish curry with rice, Bebinca cake, Prawn Balchão, and fresh coastal seafood.",
        "best_time": "November to February for ideal beach weather and festive vibes.",
        "shopping": "Anjuna Flea Market, Saturday Night Market, cashew nuts, and feni."
    },
    "kerala": {
        "famous_for": (
            "Kerala ('God's Own Country') is renowned for its tranquil backwaters and houseboat cruises in Alleppey, "
            "tea plantations in misty Munnar, Ayurvedic wellness therapies, and classical Kathakali dance."
        ),
        "top_places": [
            ("Alleppey Backwaters (Alappuzha)", "World-famous labyrinth of tranquil lagoons, canals, and lakes cruised on traditional Kettuvallam houseboats.", "₹6000/day cruise", "Overnight houseboat cruise, village canal life, paddy fields"),
            ("Munnar Tea Plantations", "Misty hill station situated 1600 meters above sea level carpeted in sprawling emerald tea estates.", "Free Entry", "Tea garden walks, Tea Museum, Echo Point, Mattupetty Dam"),
            ("Fort Kochi & Chinese Fishing Nets", "Historic coastal town displaying Portuguese, Dutch, and British heritage and iconic cantilevered fishing nets.", "Free Entry", "Chinese fishing nets at sunset, Mattancherry Dutch Palace, Jewish Synagogue"),
            ("Periyar National Park (Thekkady)", "Protected wildlife reserve around Periyar Lake famous for wild elephants, tigers, and bamboo rafting.", "₹45/person", "Lake boat safari, elephant viewing, spice plantation tours"),
            ("Kovalam Beach", "Crescent-shaped coastal paradise with the iconic red-and-white striped Vizhinjam Lighthouse.", "Free Entry", "Lighthouse climb, ayurvedic massages, beachside dining"),
            ("Varkala Cliff & Papanasam Beach", "Stunning red laterite cliffs bordering the Arabian Sea with natural mineral springs.", "Free Entry", "Cliff-top cafes, sunset beach views, natural mineral spring bath"),
            ("Athirappilly Waterfalls", "Known as the 'Niagara of India', an 80-foot waterfall cascading through lush Sholayar rainforests.", "₹50/person", "Majestic waterfalls, jungle trek to base, bird watching"),
            ("Wayanad Edakkal Caves", "Prehistoric rock-shelter caves featuring ancient petroglyphs and engravings dating back to 6000 BC.", "₹40/person", "Neolithic rock carvings, panoramic Western Ghats trekking"),
            ("Kumarakom Bird Sanctuary", "Lush bird paradise on the banks of Vembanad Lake hosting thousands of migratory species.", "₹50/person", "Migratory Siberian storks, lake canoe rides"),
            ("Kathakali Cultural Centre (Kochi)", "Traditional theater staging classical Kathakali dance-drama with elaborate makeup demonstrations.", "₹350/person", "Live makeup application, classical mudras, ancient storytelling")
        ],
        "food": "Kerala Sadya on banana leaf, Appam with vegetable stew, Malabar Parotta, and Karimeen Pollichathu.",
        "best_time": "September to March for pleasant temperatures and tranquil backwater cruises.",
        "shopping": "Fresh spices (cardamom, pepper, cinnamon), Munnar tea leaves, and coir handicrafts."
    },
    "kolkata": {
        "famous_for": (
            "Kolkata, India's City of Joy and cultural capital, is famous for its grand colonial architecture (Victoria Memorial), "
            "Howrah Bridge, Durga Puja celebrations, historic tramways, literary heritage (Rabindranath Tagore), and mouthwatering sweets."
        ),
        "top_places": [
            ("Victoria Memorial", "Majestic white Makrana marble monument and museum dedicated to Queen Victoria, surrounded by 64 acres of gardens.", "₹50/person", "Royal gallery, night illumination, lush gardens"),
            ("Howrah Bridge (Rabindra Setu)", "Iconic cantilever steel bridge spanning the Hooghly River, carrying over 100,000 vehicles daily without nuts or bolts.", "Free Entry", "Hooghly river views, evening bridge lights"),
            ("Dakshineswar Kali Temple", "19th-century temple on the Hooghly riverbank dedicated to Goddess Bhavatarini, closely associated with saint Ramakrishna Paramahamsa.", "Free Entry", "12 Shiva temples, Ramakrishna's room, river ghats"),
            ("Indian Museum", "Ninth oldest regular museum of the world, housing rare antiques, Mughal paintings, fossils, and an Egyptian mummy.", "₹50/person", "Egyptian mummy, Ashoka capital replica, dinosaur fossils"),
            ("Princep Ghat", "Historic Palladian porch ghat along the Hooghly river named after James Prinsep, famous for peaceful wooden boat rides.", "Free Entry", "Wooden boat ride under Vidyasagar Setu, sunset views"),
            ("St. Paul's Cathedral", "First Episcopal Church of the Eastern world displaying Indo-Gothic architecture and stained glass windows.", "Free Entry", "Stained glass art, Gothic arches, serene prayer hall"),
            ("Kumartuli Idol Colony", "Traditional potters' quarter where generations of clay artisans sculpt magnificent Durga Puja idols.", "Free Entry", "Clay sculpting workshops, photography, artisan culture"),
            ("Marble Palace", "19th-century neoclassical mansion filled with marble statues, chandeliers, and European paintings by Rubens.", "Free Entry (Permit)", "Art collection, marble sculptures, private aviary"),
            ("Kalighat Temple", "Ancient Shakti Peetha dedicated to Goddess Kali, from which the name Kolkata is derived.", "Free Entry", "Sacred Kali darshan, old city atmosphere"),
            ("Park Street & College Street", "Park Street for iconic dining (Flurys, Peter Cat) and College Street (Boi Para) — the world's largest second-hand book market.", "Free Entry", "Coffee House intellectual culture, book browsing, Chelo Kebabs")
        ],
        "food": "Rosogolla, Sondesh, spicy Kathi Rolls at Nizam's, Phuchka (Kolkata pani puri), Fish Curry with Gobindobhog rice, and Mishti Doi.",
        "best_time": "October to March during Durga Puja and cooler winter months.",
        "shopping": "New Market (Sir Stuart Hogg Market) for clothes and terracotta, Gariahat for handloom sarees, and College Street for books."
    },
    "bangalore": {
        "famous_for": (
            "Bangalore (Bengaluru), the 'Silicon Valley of India' and 'Garden City', is famous for its lush parks (Lalbagh, Cubbon Park), "
            "Tudor-style Bangalore Palace, vibrant craft microbreweries, pleasant year-round climate, and legendary filter coffee."
        ),
        "top_places": [
            ("Bangalore Palace", "Tudor-style royal palace inspired by Windsor Castle featuring fortified towers, battlements, and wood carvings.", "₹250/person", "Royal durbar hall, vintage photo gallery, audio tour"),
            ("Lalbagh Botanical Garden", "Historic 240-acre botanical garden commissioned by Hyder Ali, featuring a 19th-century glass house and ancient 3000-million-year-old rock.", "₹25/person", "Glass House flower shows, bonsai garden, Lalbagh rock"),
            ("Cubbon Park", "300-acre green lung in the heart of Bangalore surrounded by heritage government buildings like Vidhana Soudha.", "Free Entry", "Lush tree canopy, weekend dog park, bamboo groves"),
            ("Vidhana Soudha", "Seat of the Karnataka state legislature built in Neo-Dravidian style with the motto 'Government's Work is God's Work'.", "External View", "Evening illumination, grand Dravidian facade"),
            ("Tipu Sultan's Summer Palace", "Two-story palace built entirely of teakwood featuring carved pillars, floral motifs, and arches.", "₹20/person", "Teakwood architecture, historic museum, Persian inscriptions"),
            ("ISKCON Temple Bangalore", "Magnificent modern temple complex situated on Hare Krishna Hill featuring a gold-plated flag post.", "Free Entry", "Vedic museum, kirtan hall, delicious prasadam"),
            ("Bannerghatta Biological Park", "Expansive biological park featuring a zoo, butterfly conservatory, and wildlife safari with tigers and lions.", "₹350/safari", "Lion and tiger safari, butterfly park, zoo"),
            ("Commercial Street & Brigade Road", "Bustling shopping hubs for fashion, footwear, electronics, and street delicacies.", "Free Entry", "High street shopping, vintage cafes, buzzing vibe"),
            ("Nandi Hills", "Ancient hill fortress 60 km from Bangalore famous for sunrise viewpoints above the clouds.", "₹20/person", "Sunrise view above clouds, Tipu's Drop, ancient temple"),
            ("UB City", "Luxury commercial and dining destination featuring open-air rooftop lounges and art galleries.", "Free Entry", "Rooftop dining, luxury shopping, modern architecture")
        ],
        "food": "Crispy Benne Dosa (Butter Dosa), Filter Coffee at CTR/Vidyarthi Bhavan, Bisi Bele Bath, Mangalore Buns, and Mysore Pak.",
        "best_time": "October to February when the weather is cool and breezy.",
        "shopping": "Commercial Street, Brigade Road, Chickpet for silk sarees, and Malleswaram 8th Cross."
    },
    "hyderabad": {
        "famous_for": (
            "Hyderabad, the 'City of Pearls', is celebrated for the iconic 16th-century Charminar, the impregnable Golconda Fort, "
            "Nizami palaces (Chowmahalla), natural pearls, and world-renowned Hyderabadi Dum Biryani."
        ),
        "top_places": [
            ("Charminar", "Iconic 1591 monument with four 56-meter minarets built by Sultan Muhammad Quli Qutb Shah at the center of the old city.", "₹25/person", "Upper balcony views, Laad Bazaar bangle shopping"),
            ("Golconda Fort", "Colossal medieval fortress renowned for its acoustic engineering (a handclap at the gate can be heard at the hilltop citadel 1 km away).", "₹25/person", "Acoustic clap system, Fateh Darwaza, evening light & sound show"),
            ("Chowmahalla Palace", "Opulent palace of the Nizams of Hyderabad featuring neoclassical courtyards, marble durbar halls, and vintage Rolls-Royce cars.", "₹80/person", "Khilwat Durbar Hall, 1912 Nizam's Rolls-Royce, chandeliers"),
            ("Hussain Sagar Lake & Buddha Statue", "Large heart-shaped artificial lake featuring a monolithic 18-meter stone Buddha statue on Gibraltar Rock.", "Free (Boat ₹50)", "Ferry boat to Buddha statue, lakeside Necklace Road drive"),
            ("Salar Jung Museum", "One of the three National Museums of India housing the personal collection of Nawab Mir Yousuf Ali Khan (Salar Jung III).", "₹50/person", "Veiled Rebecca marble statue, musical mechanical clock, jade daggers"),
            ("Qutb Shahi Tombs", "Historic domed royal tombs of the Qutb Shahi dynasty set in landscaped Ibrahim Bagh gardens.", "₹25/person", "Persian and Hindu architectural synthesis, tranquil gardens"),
            ("Ramoji Film City", "World's largest integrated film studio complex (certified by Guinness World Records) spanning over 1,600 acres.", "₹1350/person", "Movie sets, live stunt shows, cinematic amusement rides"),
            ("Birla Mandir", "Stunning modern Hindu temple built of 2,000 tonnes of pure white Rajasthani marble atop Naubat Pahad.", "Free Entry", "Panoramic city & lake views, white marble carvings"),
            ("Laad Bazaar & Choodi Bazaar", "Centuries-old historic market next to Charminar famous for handcrafted lacquer and stone-studded bangles.", "Free Entry", "Lacquer bangles, bridal zardozi wear, authentic pearls"),
            ("Nehru Zoological Park", "Expansive 380-acre zoo featuring open natural moats, safari rides, and nocturnal animal house.", "₹60/person", "Lion safari, toy train, nocturnal animal exhibit")
        ],
        "food": "World-famous Hyderabadi Dum Biryani (Paradise/Bawarchi), Haleem (during Ramadan), Mirchi Ka Salan, Double Ka Meetha, Irani Chai, and Osmania biscuits.",
        "best_time": "October to March when temperatures are comfortable for exploring forts and palaces.",
        "shopping": "Laad Bazaar for stone-studded bangles, Charminar pearl shops, and Shilparamam craft village."
    },
    "amritsar": {
        "famous_for": (
            "Amritsar, the spiritual and cultural heart of Sikhism, is world-famous for the Golden Temple (Harmandir Sahib), "
            "the poignant Jallianwala Bagh memorial, the patriotic Wagah Border Beating Retreat ceremony, and mouthwatering Punjabi food."
        ),
        "top_places": [
            ("Golden Temple (Harmandir Sahib)", "Holiest gurdwara of Sikhism covered in 750 kg of pure gold leaf, surrounded by the Amrit Sarovar (Pool of Nectar).", "Free Entry", "Golden sanctum, world's largest community langar feeding 100k people daily, sacred sarovar"),
            ("Jallianwala Bagh", "Historic public garden and national memorial commemorating the tragic 1919 massacre, featuring bullet-marked walls and the Martyrs' Well.", "Free Entry", "Bullet marks on walls, Martyrs' Well, eternal flame memorial"),
            ("Wagah Border Ceremony", "Electrifying daily military ceremony at sunset on the India-Pakistan border featuring synchronized high kicks and flag lowering.", "Free Entry", "Patriotic crowd chants, military drill, flag lowering ceremony"),
            ("Partition Museum", "World's first museum dedicated to the 1947 Partition of India, housed in the historic Town Hall.", "₹10/person", "Oral history recordings, refugee artifacts, Gallery of Hope"),
            ("Gobindgarh Fort", "18th-century military fortress built by Gujjar Singh and fortified by Maharaja Ranjit Singh, featuring a coin museum and laser shows.", "₹150/person", "Toshakhana (royal treasury), 7D movie show, martial arts displays"),
            ("Durgiana Temple", "Revered 16th-century Hindu temple dedicated to Goddess Durga, featuring golden architecture rising from a sacred lake.", "Free Entry", "Silver carved doors, temple sarovar, quiet devotion"),
            ("Ram Tirath Ashram", "Ancient hermitage believed to be the ashram of sage Valmiki where Sita took refuge and gave birth to Luv and Kush.", "Free Entry", "Valmiki temple, sacred sarovar, ancient mythological site"),
            ("Sada Pind Ethnic Village", "Living Punjabi heritage village showcasing traditional mud homes, folk dances (Bhangra/Giddha), and Punjabi crafts.", "₹750/person", "Bhangra performances, camel rides, Makki Di Roti with Sarson Da Saag"),
            ("Hall Bazaar & Katra Jaimal Singh", "Bustling markets famous for traditional Phulkari embroidery, handcrafted leather juttis, and brass utensils.", "Free Entry", "Phulkari dupattas, Amritsari juttis, Papad-Wadiyan"),
            ("Kesar Da Dhaba & Lawrence Road", "Centuries-old legendary eateries serving authentic slow-cooked Dal Makhani and piping-hot Amritsari Kulcha.", "Free Entry (Dining)", "Dal Makhani cooked for 24 hours, butter-soaked Kulcha, thick Lassi")
        ],
        "food": "Crisp Amritsari Kulcha with Chole and tamarind chutney, 24-hour slow-cooked Dal Makhani at Kesar Da Dhaba, Makki Di Roti with Sarson Da Saag, and rich sweet Lassi.",
        "best_time": "October to March for cool, pleasant weather.",
        "shopping": "Hall Bazaar for Phulkari embroidered shawls and dupattas, Katra Jaimal Singh for Punjabi juttis, and papad-wadiyan."
    },
    "udaipur": {
        "famous_for": (
            "Udaipur, the 'City of Lakes' and 'Venice of the East', is famous for its romantic white marble palaces, "
            "Lake Pichola, City Palace, heritage havelis, and stunning sunset views over the Aravalli hills."
        ),
        "top_places": [
            ("City Palace Udaipur", "Rajasthan's largest royal palace complex perched on the banks of Lake Pichola, built over 400 years.", "₹300/person", "Sheesh Mahal, Mor Chowk peacock courtyard, Lake Pichola view"),
            ("Lake Pichola & Lake Palace (Taj)", "Picturesque 14th-century freshwater lake featuring the floating white marble Taj Lake Palace and Jag Mandir island.", "Boat ₹400", "Sunset boat ride, Jag Mandir island stop, palace reflections"),
            ("Jag Mandir Island Palace", "17th-century island palace in Lake Pichola with marble elephant statues, which once sheltered Mughal Prince Khurram (Shah Jahan).", "Included in boat", "Carved marble elephants, lakefront gardens, courtyards"),
            ("Saheliyon Ki Bari (Courtyard of Maidens)", "Ornate royal garden built for royal ladies featuring lotus pools, marble pavilions, and natural rain fountains.", "₹20/person", "Fountain system running on gravity, marble elephants, bougainvillea"),
            ("Bagore Ki Haveli", "18th-century mansion at Gangaur Ghat with 138 rooms, now a museum hosting the Dharohar evening folk dance show.", "₹100/person", "Dharohar evening folk dance, world's largest turban, puppet show"),
            ("Monsoon Palace (Sajjangarh)", "Hilltop fortress perched 944 meters above sea level in the Aravalli hills designed to track monsoon clouds.", "₹100/person", "Breathtaking sunset vistas over Udaipur lakes, palace illumination"),
            ("Fateh Sagar Lake & Nehru Park", "Scenic artificial lake with an island garden park (Nehru Park) accessed by speedboats.", "Free (Boat ₹100)", "Lakeside sunset drive, speedboating, Mumbai Market street food"),
            ("Jagdish Temple", "Magnificent 1651 Indo-Aryan temple dedicated to Lord Vishnu, featuring a 79-foot carved spire and brass Garuda statue.", "Free Entry", "Intricate stone carvings of dancers and elephants, morning aarti"),
            ("Karni Mata Ropeway & Viewpoint", "Cable car to the hilltop temple offering panoramic 360-degree aerial views of Lake Pichola and the City Palace.", "₹100/person", "Ropeway cable car ride, sunset aerial photography"),
            ("Shilpgram Crafts Village", "Rural arts and crafts complex 3 km outside Udaipur representing traditional lifestyle and folk crafts of western India.", "₹50/person", "Traditional mud huts, potter workshops, folk music and dance")
        ],
        "food": "Dal Baati Churma, Gatte Ki Sabzi, Ker Sangri, spicy Laal Maas, and Kachori with sweet Jalebi.",
        "best_time": "October to March for pleasant temperatures suited for boating and palace walks.",
        "shopping": "Hathi Pol Bazaar for Rajasthani miniature paintings and Pichwai art, Bada Bazaar for leather diaries and bandhani."
    },
    "vadodara": {
        "famous_for": (
            "Vadodara is Gujarat's cultural capital, celebrated for the magnificent Laxmi Vilas Palace (4 times the size of Buckingham Palace), "
            "Sayaji Baug, Baroda Museum, and serving as the primary hub to visit the Statue of Unity in Kevadia."
        ),
        "top_places": [
            ("Laxmi Vilas Palace", "Indo-Saracenic palace built in 1890 for Maharaja Sayajirao Gaekwad III, four times the size of Buckingham Palace.", "₹250/person", "Durbar Hall with Belgian stained glass, royal armory, audio tour"),
            ("Sayaji Baug & Toy Train", "Sprawling 113-acre public park featuring a floral clock, planetarium, zoo, and narrow-gauge toy train.", "Free Entry", "Sayaji toy train ride, Sardar Patel planetarium, botanical garden"),
            ("Baroda Museum & Picture Gallery", "Museum founded in 1894 modeled on London's V&A Museum, housing an Egyptian mummy and European masters.", "₹25/person", "Egyptian mummy, Akota bronze statues, European oil paintings"),
            ("Kirti Mandir", "Memorial complex erected in 1936 to honor the Gaekwad rulers, decorated with murals by painter Nandalal Bose.", "Free Entry", "Nandalal Bose murals, marble cenotaphs, bronze carvings"),
            ("EME Temple (Dakshinamurthy Temple)", "Unique modern temple built by the Indian Army Electrical & Mechanical Corps with geodesic aluminum architecture.", "Free Entry", "Geodesic aluminum dome, secular architectural elements, peaceful garden"),
            ("Champaner-Pavagadh (UNESCO)", "UNESCO World Heritage archaeological park 45 km from Vadodara featuring 8th–14th century forts, mosques, and Kalika Mata temple.", "₹40/person", "Jami Masjid architecture, Pavagadh ropeway, ancient fortifications"),
            ("Sursagar Lake", "Large lake in the heart of Vadodara featuring a magnificent 120-foot statue of Lord Shiva in the center.", "Free Entry", "120-foot Lord Shiva statue, evening lake promenade, night lighting"),
            ("Maharaja Fateh Singh Museum", "Museum situated within palace grounds housing royal collections of European paintings and sculptures.", "₹80/person", "Paintings by Raja Ravi Varma, European porcelain and bronze"),
            ("Tambekar Wada", "Traditional 19th-century Marathi-style wooden townhouse renowned for delicate wall paintings and wood carvings.", "Free Entry", "19th-century murals from Mahabharata and Anglo-Maratha wars"),
            ("Mandvi Gate & Old City Bazaars", "Historic Mughal gate at the center of the walled city leading to famous markets like Lehripura and Raopura.", "Free Entry", "Lehripura bazaar shopping, street food, Gujarati bandhani")
        ],
        "food": "Sev Usal (Mahakali Sev Usal), authentic Gujarati Thali, Khaman Dhokla, Bhakarwadi, and Duliram Penda.",
        "best_time": "October to March, especially during the 9 nights of Navratri Garba celebrations.",
        "shopping": "Bandhani dupattas, embroidered Chaniya Cholis, traditional Gujarati snacks, and silverware."
    },
    "kevadia": {
        "famous_for": (
            "Kevadia (Ekta Nagar) is world-famous for the Statue of Unity — the world's tallest statue (182m) honoring Sardar Vallabhbhai Patel, "
            "the Sardar Sarovar Dam, Valley of Flowers, Jungle Safari, and the evening projection laser show."
        ),
        "top_places": [
            ("Statue of Unity & Viewing Gallery", "World's tallest statue standing 182 meters tall on the Narmada River, dedicated to Sardar Vallabhbhai Patel.", "₹150/viewing ₹380", "153-meter high chest viewing gallery, Sardar Patel museum, high-speed elevators"),
            ("Statue of Unity Laser Light & Sound Show", "Mesmerizing evening projection mapping show on the surface of the 182-meter statue narrating India's unification.", "Included in ticket", "30-minute laser projection, synchronized sound and narration"),
            ("Sardar Sarovar Dam Viewpoint", "One of the largest concrete gravity dams in the world spanning the sacred Narmada River.", "Included in ticket", "Panoramic dam viewpoint, roaring water spillways"),
            ("Valley of Flowers (Bharat Van)", "Lush 24-acre landscaped garden featuring over 300 species of flowers, selfie spots, and walking trails.", "Included in ticket", "Colorful flower carpets, scenic walking trails, view of Statue of Unity"),
            ("Jungle Safari & Geodesic Aviary", "State-of-the-art zoological park featuring indigenous and exotic animals and two massive geodesic aviaries.", "₹200/person", "Walk-through bird aviary, Indian and African wildlife, battery car tour"),
            ("Miyawaki Forest & Maze Garden", "Dense Japanese-method afforestation park and a labyrinth maze garden spread over 3 acres.", "₹100/person", "Maze puzzle adventure, dense native forest paths"),
            ("Ekta Nursery & Craft Village", "Eco-tourism center promoting traditional tribal bamboo crafts, Bonsai making, and herbal plants.", "₹50/person", "Tribal bamboo craft souvenirs, Kadaknath chicken demo, organic cafe"),
            ("Zarwani Waterfall & Eco-Campsite", "Natural waterfall nestled inside the Shoolpaneshwar Wildlife Sanctuary ideal for gentle trekking.", "₹20/person", "Natural forest waterfall, birdwatching, eco-tourism trails"),
            ("Glow Garden", "Illuminated nighttime theme park filled with glowing flora, fauna, and interactive light installations.", "₹100/person", "Nighttime neon photo spots, illuminated animal sculptures"),
            ("Narmada River Cruise (Ekta Cruise)", "Scenic ferry cruise along the Narmada River offering majestic riverfront views of the Statue of Unity.", "₹413/person", "40-minute river cruise, onboard dinner options, sunset views")
        ],
        "food": "Ekta Food Court multi-cuisine delicacies, Gujarati farsan, regional tribal cuisine, and local Narmada valley refreshments.",
        "best_time": "October to March for comfortable outdoor temperatures around the monument.",
        "shopping": "Tribal handicrafts, souvenirs, and miniature Statue of Unity models at Ekta Mall."
    },
    "paris": {
        "famous_for": (
            "Paris is famous for the Eiffel Tower, Louvre Museum (Mona Lisa), Notre-Dame Cathedral, "
            "Champs-Élysées, Arc de Triomphe, Montmartre, and world-class culinary excellence."
        ),
        "top_places": [
            ("Eiffel Tower", "Iconic 330-meter wrought-iron lattice tower offering panoramic views across Paris.", "€18-€28", "Top floor summit, glass floor on level 1, champagne bar"),
            ("Louvre Museum", "World's most visited art museum, home to the Mona Lisa and Venus de Milo.", "€22/person", "Mona Lisa, Winged Victory, glass pyramid entrance"),
            ("Cathédrale Notre-Dame de Paris", "Masterpiece of French Gothic architecture on Île de la Cité.", "Free Entry", "Rose windows, Gothic facade, bell towers"),
            ("Arc de Triomphe & Champs-Élysées", "Triumphal arch honoring those who fought for France, at the end of the famous avenue.", "€16/person", "Panoramic rooftop view, Tomb of the Unknown Soldier"),
            ("Sacré-Cœur & Montmartre", "White-domed basilica on the highest point in Paris overlooking the bohemian artists' village.", "Free Entry", "Panoramic view from dome, Place du Tertre artists"),
            ("Musée d'Orsay", "Beaux-Arts railway station converted into a museum of Impressionist masterpieces by Monet, Van Gogh, and Renoir.", "€16/person", "Van Gogh self-portrait, Monet water lilies, giant clock window"),
            ("Palace of Versailles", "Opulent royal chateau featuring the Hall of Mirrors and magnificent French gardens.", "€21/person", "Hall of Mirrors, Royal Apartments, musical fountain gardens"),
            ("Seine River Cruise (Bateaux Mouches)", "Scenic boat tour along the Seine viewing historic bridges and illuminated monuments.", "€15/person", "Pont Neuf, Notre-Dame view from water, evening cruise"),
            ("Sainte-Chapelle", "13th-century royal Gothic chapel famous for 1,113 stained glass windows reaching 15 meters high.", "€13/person", "Breathtaking stained glass, royal relics"),
            ("Le Marais & Place des Vosges", "Historic fashionable district with medieval mansions, trendy boutiques, and Paris's oldest planned square.", "Free Entry", "Victor Hugo's house, falafel on Rue des Rosiers, art galleries")
        ],
        "food": "Fresh croissants, macarons from Ladurée, French crêpes, cheese boards, and classic baguettes.",
        "best_time": "April to June or September to October for great weather and sightseeing.",
        "shopping": "Galeries Lafayette, luxury boutiques along Champs-Élysées, and vintage flea markets."
    },
    "tokyo": {
        "famous_for": (
            "Tokyo is world-famous for blending futuristic neon skyscrapers with historic shrines (Senso-ji, Meiji Jingu), "
            "vibrant districts like Shibuya Crossing and Akihabara, and unmatched cuisine."
        ),
        "top_places": [
            ("Sensō-ji Temple (Asakusa)", "Tokyo's oldest and most significant Buddhist temple, approached through the iconic Kaminarimon Gate.", "Free Entry", "Kaminarimon red lantern, Nakamise shopping street"),
            ("Shibuya Crossing & Hachiko Statue", "World's busiest pedestrian crossing where up to 3,000 people cross simultaneously.", "Free Entry", "Scramble crossing view from Starbucks, loyal dog Hachiko bronze"),
            ("Meiji Jingu Shrine", "Serene Shinto shrine dedicated to Emperor Meiji set in a dense 170-acre evergreen forest in Harajuku.", "Free Entry", "Massive wooden torii gates, wishing tablets, peaceful forest walks"),
            ("Tokyo Skytree", "Tallest tower in the world (634m) offering 360-degree views of Tokyo and Mount Fuji on clear days.", "¥2100/person", "Tembo Deck (350m), glass floor walk, Tokyo Solamachi mall"),
            ("Akihabara Electric Town", "Global capital of electronics, anime, manga, and retro video game culture.", "Free Entry", "Manga shops, maid cafes, vintage video game stores"),
            ("Shinjuku Gyoen National Garden", "Sprawling 144-acre park combining traditional Japanese, English, and French landscaped gardens.", "¥500/person", "Cherry blossoms in spring, greenhouse, traditional teahouse"),
            ("Tsukiji Outer Market", "Bustling foodie haven of fresh sushi, grilled seafood skewers, tamagoyaki, and street treats.", "Free Entry", "Fresh tuna sashimi, wagyu skewers, Japanese kitchen knives"),
            ("teamLab Planets / Borderless", "World-renowned immersive digital art museum featuring walk-through water and light projections.", "¥3800/person", "Floating flower garden, infinite crystal universe, interactive light"),
            ("Roppongi Hills & Tokyo City View", "Modern multi-use complex with Mori Art Museum and open-air rooftop sky deck overlooking Tokyo Tower.", "¥2000/person", "Sky Deck Tokyo Tower view, modern art exhibitions"),
            ("Harajuku (Takeshita Street)", "Epicenter of Tokyo's youth culture and extreme fashion, lined with colorful crepe stalls.", "Free Entry", "Kawaii fashion, giant rainbow cotton candy, vintage fashion")
        ],
        "food": "Authentic ramen, Tsukiji sushi, yakitori, matcha desserts, and tempura.",
        "best_time": "March to May (cherry blossoms) or October to November (autumn foliage).",
        "shopping": "Ginza for high-end fashion, Akihabara for electronics, and Shibuya 109."
    }
}

def find_matching_place(
    query: str, 
    itinerary: Optional[Itinerary] = None, 
    history: Optional[List[Dict[str, Any]]] = None
) -> Optional[Dict[str, Any]]:
    """
    Intelligently identifies which landmark or attraction the user is referring to,
    handling unspaced names (e.g. 'tajmahal', 'agrafort'), partial tokens,
    itinerary stops, SAMPLE_POIS database across all cities, conversation history,
    and pronouns ('it', 'this place').
    """
    from poi_db import SAMPLE_POIS

    lower_q = query.lower().strip()
    clean_q = re.sub(r'[^a-z0-9]', '', lower_q)

    def format_place(name, full_name, category, city, cost, desc, stop_obj=None):
        raw_city = city or (itinerary.metadata.destination if itinerary and itinerary.metadata else "")
        clean_city = raw_city.split(" to ")[-1].strip() if " to " in raw_city else raw_city
        return {
            "name": name,
            "full_name": full_name,
            "category": category or "Landmarks",
            "city": clean_city,
            "cost": float(cost or 0),
            "description": desc or "",
            "notes": desc or "",
            "stop_obj": stop_obj
        }

    # Guard against list requests and 'another place' queries so they don't lock onto a single stop or old history
    if re.search(r'\b(top\s*\d+|list\s*(of)?|places to visit|attractions in|sightseeing in|spots in|all places|best places)\b', lower_q):
        return None
    if re.search(r'\b(another|next|other|different|more|else)\s*(place|spot|attraction|monument|option|location|destination|stop)?\b', lower_q) and not any(p in lower_q for p in ["tell me more", "more info", "more details"]):
        return None

    city_names = {
        "chennai", "delhi", "varanasi", "kashi", "agra", "jaipur", "mumbai", "goa", "kerala",
        "kolkata", "bangalore", "bengaluru", "hyderabad", "amritsar", "udaipur", "vadodara",
        "kevadia", "paris", "tokyo"
    }

    # 1. Search directly in current itinerary stops
    if itinerary and itinerary.days:
        for day in itinerary.days:
            for stop in day.stops:
                raw_act = stop.activity
                core_act = raw_act.split('(')[0].split('&')[0].strip()
                clean_core = re.sub(r'[^a-z0-9]', '', core_act.lower())
                clean_raw = re.sub(r'[^a-z0-9]', '', raw_act.lower())

                if (clean_core and len(clean_core) >= 4 and clean_core in clean_q) or \
                   (clean_raw and len(clean_raw) >= 4 and clean_raw in clean_q) or \
                   (core_act.lower() in lower_q and len(core_act) >= 4):
                    return format_place(core_act, raw_act, stop.category, None, stop.estimated_cost, stop.notes, stop)

    # 2. Search across SAMPLE_POIS database across all cities (avoid matching purely on city name)
    for city_key, pois in SAMPLE_POIS.items():
        for poi in pois:
            raw_name = poi["name"]
            core_name = raw_name.split('(')[0].split('&')[0].strip()
            clean_core = re.sub(r'[^a-z0-9]', '', core_name.lower())
            clean_raw = re.sub(r'[^a-z0-9]', '', raw_name.lower())

            # Skip matching if query only contains the city name
            if clean_core in city_names or clean_raw in city_names:
                continue

            if (clean_core and len(clean_core) >= 5 and clean_core in clean_q) or \
               (clean_raw and len(clean_raw) >= 5 and clean_raw in clean_q):
                return format_place(core_name, raw_name, poi.get("category"), poi.get("city", city_key.capitalize()), poi.get("avg_cost"), poi.get("description"))

    # 3. Clean query to extract requested landmark name (e.g. "link of fatehpur sikri" -> "fatehpur sikri")
    cleaned = lower_q
    for filler in [
        r'\bcan you\b', r'\bcould you\b', r'\bplease\b', r'\bgive me\b', r'\bsend me\b',
        r'\bsend\b', r'\bshow me\b', r'\bshow\b', r'\blink of\b', r'\blink for\b', r'\blink\b',
        r'\burl of\b', r'\bwebsite of\b', r'\bwebsite for\b', r'\bwebsite\b', r'\bredirect me to\b',
        r'\bredirect to\b', r'\bredirect\b', r'\bphotos of\b', r'\breviews of\b', r'\bdetails on\b',
        r'\bdetails of\b', r'\bmore info on\b', r'\bmore info about\b', r'\btell me more about\b',
        r'\btell me about\b', r'\bwhat about\b', r'\bhow to visit\b', r'\bthe\b', r'\bof\b', r'\bfor\b',
        r'\bto\b', r'\ba\b', r'\ban\b', r'\bin\b', r'\bat\b'
    ]:
        cleaned = re.sub(filler, ' ', cleaned)
    cleaned = cleaned.strip(" ?.!:,;\"'")
    if cleaned and len(cleaned) >= 3 and not re.search(r'^(it|this|that|here|place|this place|that place|the place|spot|trip|schedule)$', cleaned):
        clean_target_q = re.sub(r'[^a-z0-9]', '', cleaned)
        if clean_target_q not in city_names:
            for city_key, pois in SAMPLE_POIS.items():
                for poi in pois:
                    p_core = poi["name"].split('(')[0].split('&')[0].strip()
                    p_clean = re.sub(r'[^a-z0-9]', '', p_core.lower())
                    if p_clean and (p_clean == clean_target_q or (len(clean_target_q) >= 6 and clean_target_q in p_clean and len(clean_target_q) >= len(p_clean) * 0.5)):
                        return format_place(p_core, poi["name"], poi.get("category"), poi.get("city", city_key.capitalize()), poi.get("avg_cost"), poi.get("description"))

    # 4. Contextual History Inspection: if user is asking "tell me more" or "what is it famous for", check previous turns
    has_pronoun_reference = bool(
        re.search(r'\b(it|this|that|here|this place|that place|the place|spot)\b', lower_q) or
        any(p in lower_q for p in ["tell me more", "more details", "more info", "about it", "about this"])
    )
    if history and has_pronoun_reference:
        for prev in reversed(history[-6:]):
            prev_text = prev.get("text", "") or ""
            prev_match = find_matching_place(prev_text, itinerary, history=None)
            if prev_match:
                return prev_match

    # 5. Contextual Pronoun Fallback: ONLY if user asked using 'it', 'this place' and no history found
    if has_pronoun_reference:
        if itinerary and itinerary.days and itinerary.days[0].stops:
            first_stop = itinerary.days[0].stops[0]
            raw_act = first_stop.activity
            core_act = raw_act.split('(')[0].split('&')[0].strip()
            raw_dest = itinerary.metadata.destination if itinerary.metadata else ""
            return format_place(core_act, raw_act, first_stop.category, raw_dest, first_stop.estimated_cost, first_stop.notes, first_stop)

    return None

def chat_agent(
    itinerary: Itinerary, 
    question: str, 
    history: Optional[List[Dict[str, Any]]] = None
) -> Tuple[str, Optional[Itinerary], Optional[str]]:
    """
    Real AI Trip Copilot chatbot grounded in itinerary state, full conversation history,
    verified pricing in INR (₹), and direct Google Search and Maps links.
    """
    lower_q = question.lower().strip()
    members = itinerary.metadata.members_count if itinerary and itinerary.metadata else 1
    dest = (itinerary.metadata.destination if itinerary and itinerary.metadata else "your destination").split(" to ")[-1].strip()

    # 1. Handle polite greetings
    if lower_q in ["hi", "hello", "hey", "who are you", "what can you do", "help", "good morning", "good evening", "namaste"]:
        return f"Namaste! 🙏 I am Namaste AI, your personal travel companion. How can I assist you with your journey to {dest}?", None, None

    # 2. Polite non-travel filter (coding, math formulas, elections, crypto) - NEVER say harsh 'Irrelevant question.'
    for pattern in NON_TRAVEL_PATTERNS:
        if re.search(pattern, lower_q):
            return (
                f"Namaste! 🙏 I am Namaste AI, specialized in helping you navigate your journey to {dest}! "
                f"I can't assist with general coding or politics, but feel free to ask me anything about your attractions, schedules, directions, tickets, local food, or cultural insights!",
                None,
                None
            )

    # 3. Explicit Link / Website / Map / Redirection Request (Only when user explicitly asks for URL/link/redirect)
    is_link_request = bool(
        re.search(r'\b(redirect|take me to|open (the )?(page|site|google|map))\b', lower_q) or
        re.search(r'\b(link|url|website|web link|maps link|google link)\b', lower_q) or
        re.search(r'\b(send|give|provide|show|share)\b.*\b(link|url|website|maps|google)\b', lower_q)
    )
    if is_link_request:
        matched_place = find_matching_place(question, itinerary, history)
        if matched_place:
            p_name = matched_place["name"]
            p_city = matched_place["city"] or dest
            p_cost = matched_place["cost"]
            cost_str = f"Ticket: ₹{p_cost:,.0f}/person" if p_cost > 0 else "Free Entry"
            query_str = f"{p_name} {p_city}".strip()
            search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query_str)}"
            maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(query_str)}"
            reply = (
                f"Here are the direct links for **{p_name}** ({cost_str}):\n\n"
                f"• [{p_name} on Google Search & Photos]({search_url})\n"
                f"• [{p_name} on Google Maps Directions]({maps_url})\n\n"
                f"Click either link to explore visitor reviews, photos, and live visiting hours."
            )
            return reply, None, None
        else:
            # Check if user asked to redirect to a specific place not in database
            cand_name = re.sub(r'\b(send|give|provide|show|share|can you|could you|please|me|link|url|website|of|for|the|redirect|to|open)\b', ' ', lower_q).strip()
            target_name = cand_name.title() if cand_name and len(cand_name) >= 3 else dest
            target_city = dest if target_name != dest else ""
            query_str = f"{target_name} {target_city}".strip()
            search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query_str)}"
            maps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote_plus(query_str)}"
            reply = (
                f"Here are the direct links for **{target_name}**:\n\n"
                f"• [{target_name} on Google Search & Photos]({search_url})\n"
                f"• [{target_name} on Google Maps Directions]({maps_url})\n\n"
                f"Click either link to explore traveler reviews, photos, and guide information."
            )
            return reply, None, None

    # 4. Rescheduling / Delay questions
    if any(k in lower_q for k in ["delayed", "delay", "late", "traffic", "push everything", "push after"]):
        delay_min = 180
        m = re.search(r'(\d+)\s*(?:hour|hr)', lower_q)
        if m:
            delay_min = int(m.group(1)) * 60
        else:
            m_min = re.search(r'(\d+)\s*(?:min|minute)', lower_q)
            if m_min:
                delay_min = int(m_min.group(1))

        disrupt_type = "flight_delay" if ("flight" in lower_q or "plane" in lower_q) else ("train_delay" if ("train" in lower_q or "rail" in lower_q) else "traffic_delay")
        delay_title = f"{'Flight' if disrupt_type == 'flight_delay' else ('Train' if disrupt_type == 'train_delay' else 'Highway Traffic')} Delay ({delay_min // 60}h)" if delay_min >= 60 else f"Delay ({delay_min}m)"

        res = handle_resequence_delay(
            itinerary,
            disruption_type=disrupt_type,
            delay_minutes=delay_min,
            delay_title=delay_title,
            affected_day=1
        )
        first_shift = res["shifts"][0] if res["shifts"] else None
        new_start = first_shift["new_start"] if first_shift else "updated time"
        reply = f"Your schedule has been adjusted for the delay. Your next activity starts at {new_start}."
        return reply, res["updated_itinerary"], "resequenced_delay"

    # 5. Cancellation questions
    if any(word in lower_q for word in ["cancel", "remove", "drop", "skip", "delete"]):
        for day in itinerary.days:
            for stop in day.stops:
                if stop.status != "cancelled" and (stop.activity.lower() in lower_q or stop.id.lower() in lower_q):
                    updated_itin, summary, aff_day, alt_name = rebuild_disrupted_day(
                        itinerary, stop_id=stop.id, reason=f"User chat request: '{question}'"
                    )
                    reply = f"'{stop.activity}' has been removed from your schedule."
                    return reply, updated_itin, "cancelled_stop"

    # 6. Primary Semantic Intelligence via Gemini (Understands nuances & distinguishes different questions)
    gemini_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
    if gemini_key and gemini_key.strip() and gemini_key != "your_gemini_api_key_here":
        days_summary_lines = []
        for d in itinerary.days:
            stop_summaries = []
            for s in d.stops:
                status_str = " [CANCELLED]" if s.status == "cancelled" else ""
                cost_str = f"₹{s.estimated_cost:,.0f}/person" if s.estimated_cost > 0 else "Free entry"
                dur_str = f"{s.estimated_duration} mins" if s.estimated_duration else ""
                notes_str = f" | Notes: {s.notes}" if s.notes else ""
                stop_summaries.append(
                    f"    - {s.time_slot.start}-{s.time_slot.end}: {s.activity} ({s.category}, Ticket: {cost_str}, {dur_str}){status_str}{notes_str}"
                )
            days_summary_lines.append(f"  Day {d.day_number} ({d.date}) - Theme: '{d.theme}':\n" + "\n".join(stop_summaries))
        days_context = "\n".join(days_summary_lines)

        t = itinerary.metadata.transportation
        transit_str = f"{t.mode.capitalize()} via {t.route_name} ({t.carrier_info})" if t else itinerary.metadata.travel_mode

        history_lines = []
        if history:
            for h in history[-8:]:
                r_name = "User" if h.get("role") == "user" else "Assistant"
                t_val = h.get("text", "")
                if t_val:
                    history_lines.append(f"{r_name}: {t_val}")
        history_context = "\n".join(history_lines) if history_lines else "(No previous questions in this session yet)"

        matched_p = find_matching_place(question, itinerary, history)
        place_hint = ""
        if matched_p:
            p_name = matched_p["name"]
            p_city = matched_p["city"] or dest
            place_hint = (
                f"\nContext on place referenced: {p_name} ({p_city})\n"
                f"Description: {matched_p.get('description', '')}\n"
                f"Verified ticket: ₹{matched_p.get('cost', 0):,.0f}/person\n"
            )

        sys_inst = (
            "You are Namaste AI (🙏) — an expert, culturally knowledgeable, friendly Indian travel companion for TripSaathi.\n\n"
            "CRITICAL INSTRUCTIONS:\n"
            "1. UNDERSTAND THE QUESTION CAREFULLY: Read the user's question with utmost care. Understand its exact intent and distinguish it from previous questions or other topics.\n"
            "2. CLEAR DIFFERENTIATION:\n"
            "   - Ticket price/entry fee of a specific attraction vs. the total overall trip budget (do NOT confuse them).\n"
            "   - Local commuting in the city (auto-rickshaw, taxi, walking, metro) vs. the intercity travel corridor.\n"
            "   - Day 1 vs. Day 2 vs. Day 3 schedule or morning vs. afternoon/evening plans.\n"
            "   - Historical facts vs. food recommendations vs. shopping markets.\n"
            "   - Clothing & dress code etiquette vs. weather forecast.\n"
            "   - When comparing places or days, highlight their distinct differences.\n"
            "3. GROUNDED IN ITINERARY: When asked about scheduled activities, times, stops, or costs, refer accurately to the itinerary data provided.\n"
            "4. CULTURAL & PRACTICAL INSIGHTS: Provide authentic, practical, and helpful travel tips.\n"
            "5. TONE & FORMAT: Welcoming, courteous, respectful (start naturally with 'Namaste! 🙏'). Use clean markdown with bolding and bullet points. Keep responses focused and readable (2-4 paragraphs or clear bullet lists).\n"
            "6. CURRENCY: Always use Indian Rupees (₹).\n"
            "7. NO LINKS UNLESS ASKED: Do NOT include URLs or links unless the user explicitly asked for a link, website, or redirection.\n"
            "8. OFF-TOPIC QUESTIONS: If asked something completely outside travel (coding, math, politics), politely say you specialize in their journey to " + dest + "."
        )

        user_prompt = (
            f"Trip Overview:\n"
            f"- Destination: {dest}\n"
            f"- Travel Dates: {itinerary.metadata.start_date} to {itinerary.metadata.end_date} ({members} members)\n"
            f"- Intercity Transit: {transit_str}\n"
            f"- Total Trip Budget: ₹{itinerary.metadata.budget:,.0f} | Estimated Trip Cost: ₹{itinerary.trip_totals.estimated_total_cost:,.0f}\n\n"
            f"Day-by-Day Scheduled Stops:\n{days_context}\n"
            f"{place_hint}\n"
            f"Conversation History:\n{history_context}\n\n"
            f"Current User Question: {question}"
        )

        gemini_reply = call_gemini(user_prompt, sys_inst)
        if gemini_reply and "irrelevant question" not in gemini_reply.lower():
            return gemini_reply, None, None

    # =========================================================================
    # Fallback Rules Engine: Differentiates Question Types If AI API is Offline
    # =========================================================================
    all_known_cities = [
        "chennai", "delhi", "varanasi", "kashi", "agra", "jaipur", "mumbai", "goa", "kerala",
        "kolkata", "bangalore", "bengaluru", "hyderabad", "amritsar", "udaipur", "vadodara",
        "kevadia", "paris", "tokyo"
    ]
    mentioned_city = None
    for c in all_known_cities:
        if c in lower_q:
            mentioned_city = "varanasi" if c == "kashi" else ("bangalore" if c == "bengaluru" else c)
            break

    dest_city = None
    for c in all_known_cities:
        if c in dest.lower():
            dest_city = "varanasi" if c == "kashi" else ("bangalore" if c == "bengaluru" else c)
            break

    target_city = mentioned_city or dest_city

    # 7. Specific Stop Ticket Price vs Overall Trip Budget
    matched_place = find_matching_place(question, itinerary, history)
    if matched_place and any(w in lower_q for w in ["ticket", "entry", "fee", "cost", "price", "how much"]):
        p_cost = matched_place["cost"]
        cost_str = f"₹{p_cost:,.0f}/person (Total: ₹{p_cost * members:,.0f} for {members} members)" if p_cost > 0 else "Free Entry (no ticket required)"
        return (
            f"Namaste! 🙏 Entry ticket details for **{matched_place['name']}** in {matched_place['city'] or dest}:\n\n"
            f"• **Ticket Fee**: {cost_str}\n"
            f"• **Category**: {matched_place['category']}\n"
            f"• **Visiting Note**: {matched_place.get('description', '') or 'Make sure to carry a valid government photo ID.'}"
        ), None, None

    if any(w in lower_q for w in ["total budget", "allocated budget", "overall budget", "trip budget"]):
        return f"Namaste! 🙏 Your total allocated trip budget is ₹{itinerary.metadata.budget:,.0f} for {members} member(s).", None, None

    if any(w in lower_q for w in ["total cost", "entire cost", "trip cost", "how much overall", "estimated cost"]):
        return f"Namaste! 🙏 The estimated total trip cost is ₹{itinerary.trip_totals.estimated_total_cost:,.0f} across {itinerary.trip_totals.total_activities} scheduled stops for {members} member(s).", None, None

    # 8. Local City Commuting vs Intercity Travel Corridor
    if any(w in lower_q for w in ["cab", "taxi", "auto", "rickshaw", "metro", "locally", "get around", "commute"]):
        return (
            f"Namaste! 🙏 For getting around locally in **{dest}**:\n\n"
            f"• **App-based Cabs**: Uber and Ola are widely available for city travel.\n"
            f"• **Auto-Rickshaws & E-Rickshaws**: Best for navigating old city bazaars and narrow lanes near monuments.\n"
            f"• **Tip**: Agree on meter fare or fix the rate before boarding street autos."
        ), None, None

    if any(w in lower_q for w in ["transit", "travel mode", "flight", "road", "train", "how are we going", "how to reach"]):
        t = itinerary.metadata.transportation
        if t:
            return f"Namaste! 🙏 You are travelling to {dest} by {t.mode} via **{t.route_name}** ({t.carrier_info}).", None, None

    # 9. Schedule Questions (Tomorrow Morning vs Tomorrow vs Specific Day)
    if "tomorrow morning" in lower_q:
        target_day = itinerary.days[1] if len(itinerary.days) > 1 else itinerary.days[0]
        morning_stops = [s for s in target_day.stops if s.status != "cancelled" and any(h in s.time_slot.start for h in ["08:", "09:", "10:"])]
        if morning_stops:
            s = morning_stops[0]
            return f"Namaste! 🙏 Tomorrow morning at {s.time_slot.start}, you are scheduled to visit **{s.activity}** ({s.category}).", None, None
        first_stop = target_day.stops[0] if target_day.stops else None
        if first_stop:
            return f"Namaste! 🙏 Tomorrow morning starts at {first_stop.time_slot.start} with **{first_stop.activity}**.", None, None

    if "tomorrow" in lower_q or "day 2" in lower_q:
        target_day = itinerary.days[1] if len(itinerary.days) > 1 else itinerary.days[0]
        stops = [f"**{s.activity}** ({s.time_slot.start}-{s.time_slot.end})" for s in target_day.stops if s.status != "cancelled"]
        if stops:
            return f"Namaste! 🙏 Tomorrow (Day {target_day.day_number}) you have scheduled:\n\n" + "\n".join([f"• {st}" for st in stops]), None, None

    if "day 1" in lower_q:
        target_day = itinerary.days[0]
        stops = [f"**{s.activity}** ({s.time_slot.start}-{s.time_slot.end})" for s in target_day.stops if s.status != "cancelled"]
        return f"Namaste! 🙏 On Day 1 you have scheduled:\n\n" + "\n".join([f"• {st}" for st in stops]), None, None

    # 10. List Places Query
    is_list_places_q = bool(
        re.search(r'\b(top\s*\d+|list\s*(of)?|best places|places to visit|must visit|attractions|spots to see|what are the places|show me places)\b', lower_q) or
        (re.search(r'\bplaces\b', lower_q) and (mentioned_city or any(w in lower_q for w in ["visit", "see", "top", "good", "famous"])))
    )
    if is_list_places_q and target_city in CITY_KNOWLEDGE and CITY_KNOWLEDGE[target_city].get("top_places"):
        places_list = CITY_KNOWLEDGE[target_city]["top_places"]
        city_display = target_city.capitalize()
        lines = [f"Namaste! 🙏 Here are the top {len(places_list)} must-visit places in **{city_display}**:\n"]
        for idx, (p_name, p_desc, p_cost, p_highlight) in enumerate(places_list, 1):
            lines.append(f"{idx}. **{p_name}** ({p_cost})")
            lines.append(f"   • {p_desc}")
            lines.append(f"   • *Highlight*: {p_highlight}\n")
        lines.append("Feel free to ask 'what is [place] famous for' or request a direct map link!")
        return "\n".join(lines), None, None

    # 11. Another Place / Next Place Query
    is_next_place_q = bool(
        re.search(r'\b(another|next|other|different|one more|what else|something else)\s*(place|spot|attraction|monument|option|location|destination|stop)?\b', lower_q) and
        not any(p in lower_q for p in ["tell me more", "more info", "more details", "about it"])
    )
    if is_next_place_q and target_city in CITY_KNOWLEDGE:
        discussed = set()
        if history:
            for h in history:
                txt = (h.get("text", "") or "").lower()
                for item in CITY_KNOWLEDGE[target_city].get("top_places", []):
                    core = item[0].split("(")[0].strip().lower()
                    if core in txt:
                        discussed.add(core)
        for item in CITY_KNOWLEDGE[target_city].get("top_places", []):
            core = item[0].split("(")[0].strip().lower()
            if core not in discussed:
                p_name, p_desc, p_cost, p_highlight = item
                city_display = target_city.capitalize()
                return (
                    f"Namaste! 🙏 Here is another wonderful place to explore in **{city_display}**:\n\n"
                    f"🏛️ **{p_name}** ({p_cost})\n\n"
                    f"{p_desc}\n\n"
                    f"• **Highlight**: {p_highlight}\n"
                    f"• **Visitor Tip**: Ideal for visiting in the morning or late afternoon."
                ), None, None

    # 12. Deep-Dive Query ('what is it famous for')
    is_deep_dive_q = bool(
        re.search(r'\b(famous for|why (is|it is) famous|tell me more|what is special|history of|details of|background of)\b', lower_q) or
        (re.search(r'\b(famous|famour|famus|known for)\b', lower_q) and any(w in lower_q for w in ["it", "this", "that", "why", "what"]))
    )
    if is_deep_dive_q and matched_place:
        p_name = matched_place["name"]
        p_desc = matched_place.get("description", "")
        p_cost = f"₹{matched_place['cost']:,.0f}/person" if matched_place['cost'] > 0 else "Free Entry"
        return (
            f"Namaste! 🙏 **{p_name}** is famous for:\n\n"
            f"• **Significance**: {p_desc}\n"
            f"• **Category**: {matched_place['category']}\n"
            f"• **Ticket & Entry**: {p_cost}\n"
            f"• **Visitor Experience**: One of the most iconic highlights, known for its rich heritage and photography vantage points."
        ), None, None

    # 13. Specific Place Direct Inquiry
    if matched_place:
        p_name = matched_place["name"]
        p_city = matched_place["city"] or dest
        p_cost = matched_place["cost"]
        cost_str = f"Verified entry ticket is ₹{p_cost:,.0f}/person." if p_cost > 0 else "Entry is free."
        desc = matched_place.get("description") or f"a celebrated attraction in {p_city}."
        return (
            f"Namaste! 🙏 **{p_name}** ({p_city}) is {desc} {cost_str}\n\n"
            f"You can ask me 'what is it famous for' or 'how do we reach there'!"
        ), None, None

    # 14. Food / Weather / Shopping in City
    if target_city and target_city in CITY_KNOWLEDGE:
        c_info = CITY_KNOWLEDGE[target_city]
        city_display = target_city.capitalize()
        if any(w in lower_q for w in ["food", "eat", "dishes", "cuisine", "street food", "restaurant", "snack"]):
            return f"Namaste! 🙏 When in **{city_display}**, here are the top local specialties to try:\n\n{c_info['food']}", None, None
        if any(w in lower_q for w in ["weather", "best time", "season", "climate", "temperature", "month", "when to visit"]):
            return f"Namaste! 🙏 The best time to visit **{city_display}** is {c_info['best_time']}", None, None
        if any(w in lower_q for w in ["shopping", "market", "bazaar", "buy", "souvenir"]):
            return f"Namaste! 🙏 Top shopping spots in **{city_display}** include: {c_info['shopping']}", None, None

    # 15. Packing & Safety
    if any(w in lower_q for w in ["pack", "wear", "dress", "clothes", "clothing"]):
        return (
            f"Namaste! 🙏 Recommended packing essentials for **{dest}**:\n\n"
            f"• Comfortable footwear for walking tours and monument exploration.\n"
            f"• Modest, breathable cotton clothing suitable for sacred sites.\n"
            f"• Sun protection (sunglasses, hat, sunscreen) and a light layer for air-conditioned transit.\n"
            f"• Valid ID card and a reusable water bottle."
        ), None, None

    if any(w in lower_q for w in ["safe", "safety", "precaution", "scam", "emergency"]):
        return (
            f"Namaste! 🙏 Tips for a safe trip to **{dest}**:\n\n"
            f"• Stick to authorized counters or official apps for monument tickets.\n"
            f"• Use verified app-based cabs (Uber/Ola) or prepaid taxi/auto booths.\n"
            f"• Drink sealed bottled or filtered water.\n"
            f"• Keep emergency contacts and digital copies of your IDs handy."
        ), None, None

    # 16. Dynamic Contextual Fallback (Customized to Question and Destination)
    first_stops = [s.activity for s in itinerary.days[0].stops[:3]] if itinerary.days else []
    stops_str = ", ".join(first_stops) if first_stops else dest
    return (
        f"Namaste! 🙏 Regarding your inquiry about **'{question.strip(' ?.!')}'** for your trip to **{dest}**:\n\n"
        f"Your itinerary currently features {itinerary.trip_totals.total_activities} scheduled stops, including **{stops_str}**.\n\n"
        f"You can ask me specifically about visiting hours, ticket prices (₹), local dishes, transit options, or requesting schedule changes!"
    ), None, None
