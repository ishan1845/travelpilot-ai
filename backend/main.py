import os
import logging
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from models import (
    Itinerary, GenerateRequest, ValidateRequest, ValidateResponse,
    ChatRequest, ChatResponse, DisruptRequest, DisruptResponse,
    UpdateConstraintsRequest, UpdateConstraintsResponse, Conflict,
    ResequenceDelayRequest, ResequenceDelayResponse
)
from tools import check_conflicts
from agent import generate_itinerary_agentic, chat_agent
from disruption_engine import rebuild_disrupted_day, handle_update_constraints, handle_resequence_delay

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tripsaathi")

app = FastAPI(
    title="TripSaathi API",
    description="Intelligent Trip Planning & Disruption Management Agent API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLE_QUOTES = [
    {"quote": "Travel is fatal to prejudice, bigotry, and narrow-mindedness.", "author": "Mark Twain"},
    {"quote": "Not all those who wander are lost.", "author": "J.R.R. Tolkien"},
    {"quote": "The real voyage of discovery consists not in seeking new landscapes, but in having new eyes.", "author": "Marcel Proust"},
    {"quote": "To travel is to live.", "author": "Hans Christian Andersen"},
    {"quote": "Life is either a daring adventure or nothing at all.", "author": "Helen Keller"},
    {"quote": "Travel makes one modest. You see what a tiny place you occupy in the world.", "author": "Gustave Flaubert"}
]

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "TripSaathi Agent API", "version": "1.0.0"}

@app.get("/api/quotes")
def get_travel_quotes():
    return {"quotes": SAMPLE_QUOTES}

@app.get("/api/sample-destinations")
def get_sample_destinations():
    return {
        "destinations": [
            {"name": "Agra", "country": "India", "monument": "Taj Mahal", "suggested_budget": 15000, "interests": ["Landmarks", "Art & Culture", "Food & Dining"]},
            {"name": "Jaipur", "country": "India", "monument": "Hawa Mahal & Amber Fort", "suggested_budget": 18000, "interests": ["Landmarks", "Food & Dining", "Art & Culture"]},
            {"name": "Varanasi", "country": "India", "monument": "Ganga Ghats & Kashi Vishwanath", "suggested_budget": 14000, "interests": ["Art & Culture", "Landmarks", "Food & Dining"]},
            {"name": "Goa", "country": "India", "monument": "Baga Beach & Fort Aguada", "suggested_budget": 25000, "interests": ["Nature & Outdoors", "Food & Dining", "Entertainment"]},
            {"name": "Kerala", "country": "India", "monument": "Alleppey Backwaters & Munnar", "suggested_budget": 28000, "interests": ["Nature & Outdoors", "Food & Dining", "Landmarks"]},
            {"name": "Delhi", "country": "India", "monument": "India Gate & Qutub Minar", "suggested_budget": 16000, "interests": ["Landmarks", "Food & Dining", "Art & Culture"]},
            {"name": "Paris", "country": "France", "monument": "Eiffel Tower & Louvre", "suggested_budget": 120000, "interests": ["Art & Culture", "Food & Dining", "Landmarks"]},
            {"name": "Tokyo", "country": "Japan", "monument": "Senso-ji & Shibuya Sky", "suggested_budget": 140000, "interests": ["Landmarks", "Food & Dining", "Entertainment"]}
        ]
    }

@app.post("/itinerary/generate", response_model=Itinerary)
def generate_itinerary(request: GenerateRequest):
    """
    POST /itinerary/generate
    Generates a full day-by-day Itinerary grounded in real POI data,
    geographically clustered to minimize backtracking and with realistic travel buffers.
    """
    try:
        itin = generate_itinerary_agentic(request)
        return itin
    except Exception as e:
        logger.error(f"Error generating itinerary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/itinerary/validate", response_model=ValidateResponse)
def validate_itinerary(request: ValidateRequest):
    """
    POST /itinerary/validate
    Checks for time overlaps, activities scheduled outside opening hours,
    and unrealistic travel time between consecutive stops.
    """
    try:
        raw_conflicts = check_conflicts(request.itinerary.model_dump())
        conflicts = [Conflict(**c) for c in raw_conflicts]
        is_valid = len([c for c in conflicts if c.severity == "error"]) == 0
        summary = (
            "Itinerary is valid with no critical scheduling overlaps."
            if is_valid
            else f"Identified {len(conflicts)} scheduling issues or buffer warnings."
        )
        return ValidateResponse(
            is_valid=is_valid,
            conflicts=conflicts,
            summary=summary
        )
    except Exception as e:
        logger.error(f"Error validating itinerary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/itinerary/chat", response_model=ChatResponse)
def chat_with_agent(request: ChatRequest):
    """
    POST /itinerary/chat
    Answers natural-language questions grounded in the current itinerary state.
    If the question implies a change/cancellation, triggers the disruption rebuild engine.
    """
    try:
        reply, updated_itin, action = chat_agent(request.itinerary, request.message, history=request.history)
        return ChatResponse(
            reply=reply,
            updated_itinerary=updated_itin,
            action_taken=action
        )
    except Exception as e:
        logger.error(f"Error in chat agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/itinerary/disrupt", response_model=DisruptResponse)
def disrupt_activity(request: DisruptRequest):
    """
    POST /itinerary/disrupt
    Marks stop as 'cancelled', identifies only the affected day(s),
    suggests 1-2 concrete alternative activities near the same location/category/time using search_places,
    re-validates the day, and returns the updated Itinerary JSON plus a natural-language summary.
    Does NOT regenerate unaffected days.
    """
    try:
        updated_itin, summary, aff_day, alt_name = rebuild_disrupted_day(
            request.itinerary,
            stop_id=request.stop_id,
            reason=request.reason
        )
        return DisruptResponse(
            updated_itinerary=updated_itin,
            summary=summary,
            affected_day=aff_day,
            alternative_suggested=alt_name
        )
    except Exception as e:
        logger.error(f"Error disrupting activity: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/itinerary/update-constraints", response_model=UpdateConstraintsResponse)
def update_constraints(request: UpdateConstraintsRequest):
    """
    POST /itinerary/update-constraints
    Recomputes only the parts of the itinerary impacted by changed constraints
    (e.g., if budget drops, replaces expensive stops with cheaper alternatives).
    """
    try:
        updated_itin, summary, changes = handle_update_constraints(
            request.itinerary,
            new_budget=request.new_budget,
            new_members_count=request.new_members_count,
            new_travel_mode=request.new_travel_mode,
            new_start_date=request.new_start_date,
            new_end_date=request.new_end_date,
            new_interests=request.new_interests
        )
        return UpdateConstraintsResponse(
            updated_itinerary=updated_itin,
            summary=summary,
            changes_made=changes
        )
    except Exception as e:
        logger.error(f"Error updating constraints: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/itinerary/resequence-delay", response_model=ResequenceDelayResponse)
def resequence_delay_endpoint(request: ResequenceDelayRequest):
    """
    POST /itinerary/resequence-delay
    Living itinerary that reacts to disruption in real time.
    Detects ripple effects (e.g., flight delayed by 3 hours) and re-sequences downstream activities automatically.
    """
    try:
        response = handle_resequence_delay(
            request.itinerary,
            disruption_type=request.disruption_type,
            delay_minutes=request.delay_minutes,
            delay_title=request.delay_title,
            affected_day=request.affected_day
        )
        return response
    except Exception as e:
        logger.error(f"Error in resequence-delay: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

from pydantic import BaseModel
from typing import Optional

class LoginNotificationRequest(BaseModel):
    email: str
    name: str = "Explorer"
    provider: str = "google"
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None

@app.post("/api/auth/send-login-notification")
def send_login_notification(req: LoginNotificationRequest):
    """
    Sends a real security notification to the user's Gmail/Email confirming that
    this Google account is shared with TripSaathi Tour AI.
    """
    logger.info(f"Dispatching security notification email to: {req.email} for provider: {req.provider}")
    
    smtp_server = req.smtp_server or os.environ.get("SMTP_SERVER") or "smtp.gmail.com"
    smtp_port = req.smtp_port or int(os.environ.get("SMTP_PORT", 587))
    smtp_user = req.smtp_user or os.environ.get("SMTP_USER") or os.environ.get("GMAIL_USER") or "ishan145sharma@gmail.com"
    smtp_password = req.smtp_password or os.environ.get("SMTP_PASSWORD") or os.environ.get("GMAIL_APP_PASSWORD") or "wzvbmfectziwzaag"
    
    email_sent = False
    delivery_error = None
    
    if smtp_user and smtp_password:
        try:
            import smtplib
            import ssl
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart("alternative")
            msg['From'] = f"TripSaathi Tour AI Security <{smtp_user}>"
            msg['To'] = req.email
            msg['Subject'] = "Security Alert: Google Account Connected with TripSaathi Tour AI"
            
            text_body = f"""Hello {req.name},

Your Google Account ({req.email}) has been successfully linked and shared with TripSaathi Tour AI.

Time: Live Session
App: TripSaathi Tour AI (Bharat & Global)
Status: Account Connected

If this was you, you can safely continue exploring and planning your grounded itineraries.
If you did not authorize this, please sign out immediately from the TripSaathi navigation bar.

Warm regards,
TripSaathi Tour AI Security Team
"""
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #ECE8E1; border-radius: 16px; background-color: #ffffff;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h2 style="color: #19202E; margin: 0;">Trip<span style="color: #FA5B0F;">Saathi</span> Tour AI</h2>
                    <p style="color: #64748b; font-size: 13px; margin: 4px 0 0 0;">Grounded Multi-Modal Journey Planner</p>
                </div>
                <div style="background-color: #f8fafc; border-left: 4px solid #FA5B0F; padding: 16px; border-radius: 8px; margin-bottom: 20px;">
                    <h3 style="color: #0f172a; margin: 0 0 8px 0; font-size: 16px;">Security Alert: Account Connected</h3>
                    <p style="color: #334155; font-size: 14px; margin: 0; line-height: 1.5;">
                        Hello <strong>{req.name}</strong>, your Google account (<strong>{req.email}</strong>) is now shared and connected with TripSaathi Tour AI.
                    </p>
                </div>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px; color: #475569;">
                    <tr><td style="padding: 6px 0; font-weight: bold;">Status:</td><td style="color: #16a34a; font-weight: bold;">Active Connected Session</td></tr>
                    <tr><td style="padding: 6px 0; font-weight: bold;">Provider:</td><td>{req.provider.capitalize()} Authentication</td></tr>
                    <tr><td style="padding: 6px 0; font-weight: bold;">Platform:</td><td>TripSaathi Bharat & Global Explorer</td></tr>
                </table>
                <p style="color: #64748b; font-size: 12px; line-height: 1.5;">
                    If you authorized this sign-in, no further action is required. If you did not authorize this, please sign out immediately from the navigation bar.
                </p>
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
                <p style="color: #94a3b8; font-size: 11px; text-align: center; margin: 0;">
                    TripSaathi Tour AI • Official Security Notification
                </p>
            </div>
            """
            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))
            
            context = ssl.create_default_context()
            with smtplib.SMTP(smtp_server, smtp_port, timeout=12) as server:
                server.starttls(context=context)
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
            email_sent = True
            logger.info(f"Live SMTP email sent successfully to {req.email}")
        except Exception as e:
            delivery_error = str(e)
            logger.warning(f"SMTP send failed: {e}")
    else:
        delivery_error = "Server SMTP credentials (SMTP_USER/SMTP_PASSWORD) not configured."
        logger.info(f"No SMTP credentials provided. Automated background delivery skipped.")

    return {
        "status": "success",
        "email": req.email,
        "name": req.name,
        "provider": req.provider,
        "email_dispatched": email_sent,
        "delivery_error": delivery_error,
        "notification_message": f"Security alert: Your Google account ({req.email}) is securely shared with TripSaathi Tour AI."
    }

# Mount compiled frontend if available for unified deployment
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
if os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        target_file = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(target_file):
            return FileResponse(target_file)
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        return {"status": "Frontend build not found"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


