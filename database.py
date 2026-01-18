"""
Supabase database client for appointment management.
"""
import os
from datetime import datetime, date, time
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv("SUPABASE_URL", ""),
    os.getenv("SUPABASE_ANON_KEY", "")
)


def get_user_by_phone(phone_number: str) -> Optional[dict]:
    """Get user by phone number."""
    result = supabase.table("users").select("*").eq("phone_number", phone_number).execute()
    return result.data[0] if result.data else None


def create_user(phone_number: str, name: Optional[str] = None) -> dict:
    """Create a new user or return existing one."""
    existing = get_user_by_phone(phone_number)
    if existing:
        return existing
    
    result = supabase.table("users").insert({
        "phone_number": phone_number,
        "name": name
    }).execute()
    return result.data[0]


def check_slot_available(date_str: str, time_str: str) -> bool:
    """Check if a time slot is available (not already booked)."""
    result = supabase.table("appointments").select("id").eq(
        "date", date_str
    ).eq(
        "time", time_str
    ).eq(
        "status", "active"
    ).execute()
    return len(result.data) == 0


def book_appointment(
    user_phone: str,
    date_str: str,
    time_str: str,
    description: Optional[str] = None
) -> dict:
    """
    Book an appointment for a user.
    Returns success/failure with message.
    """
    # Check for double-booking
    if not check_slot_available(date_str, time_str):
        return {
            "success": False,
            "message": f"Sorry, the slot at {time_str} on {date_str} is already booked. Please choose another time."
        }
    
    try:
        result = supabase.table("appointments").insert({
            "user_phone": user_phone,
            "date": date_str,
            "time": time_str,
            "description": description or "General appointment",
            "status": "active"
        }).execute()
        
        return {
            "success": True,
            "message": f"Successfully booked your appointment for {date_str} at {time_str}.",
            "appointment": result.data[0] if result.data else None
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to book appointment: {str(e)}"
        }


def get_user_appointments(user_phone: str) -> list:
    """Get all appointments for a user."""
    result = supabase.table("appointments").select("*").eq(
        "user_phone", user_phone
    ).order("date", desc=False).order("time", desc=False).execute()
    return result.data


def cancel_appointment(appointment_id: str) -> dict:
    """Cancel an appointment by marking it as cancelled."""
    try:
        result = supabase.table("appointments").update({
            "status": "cancelled",
            "updated_at": datetime.now().isoformat()
        }).eq("id", appointment_id).execute()
        
        if result.data:
            return {
                "success": True,
                "message": "Appointment cancelled successfully."
            }
        return {
            "success": False,
            "message": "Appointment not found."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to cancel appointment: {str(e)}"
        }


def modify_appointment(
    appointment_id: str,
    new_date: Optional[str] = None,
    new_time: Optional[str] = None
) -> dict:
    """Modify an existing appointment's date/time."""
    # First, get the existing appointment
    existing = supabase.table("appointments").select("*").eq("id", appointment_id).execute()
    
    if not existing.data:
        return {
            "success": False,
            "message": "Appointment not found."
        }
    
    current = existing.data[0]
    target_date = new_date or current["date"]
    target_time = new_time or current["time"]
    
    # Check if new slot is available
    if not check_slot_available(target_date, target_time):
        return {
            "success": False,
            "message": f"Sorry, the slot at {target_time} on {target_date} is already booked."
        }
    
    try:
        result = supabase.table("appointments").update({
            "date": target_date,
            "time": target_time,
            "updated_at": datetime.now().isoformat()
        }).eq("id", appointment_id).execute()
        
        return {
            "success": True,
            "message": f"Appointment updated to {target_date} at {target_time}.",
            "appointment": result.data[0] if result.data else None
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to modify appointment: {str(e)}"
        }


def save_call_summary(
    user_phone: Optional[str],
    summary: str,
    appointments_discussed: list,
    preferences_mentioned: list,
    cost_breakdown: Optional[dict] = None
) -> dict:
    """Save a call summary to the database."""
    try:
        result = supabase.table("call_summaries").insert({
            "user_phone": user_phone,
            "summary": summary,
            "appointments_discussed": appointments_discussed,
            "preferences_mentioned": preferences_mentioned,
            "cost_breakdown": cost_breakdown
        }).execute()
        
        return {
            "success": True,
            "data": result.data[0] if result.data else None
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
