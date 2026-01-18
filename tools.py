"""
Tool functions for the voice agent.
These are the actions the agent can take during a conversation.
Using function_tool decorator (current livekit-agents API).
"""
from datetime import datetime, timedelta
from typing import Optional
from livekit.agents import llm
import database as db


# Store conversation context
class ConversationContext:
    def __init__(self):
        self.user_phone: Optional[str] = None
        self.user_name: Optional[str] = None
        self.appointments_discussed: list = []
        self.preferences_mentioned: list = []
        self.conversation_history: list = []
    
    def reset(self):
        self.user_phone = None
        self.user_name = None
        self.appointments_discussed = []
        self.preferences_mentioned = []
        self.conversation_history = []


# Global conversation context
context = ConversationContext()


def generate_available_slots(date_str: str) -> list[str]:
    """
    Generate available time slots for a given date.
    Slots are 30 minutes from 9 AM to 5 PM.
    """
    slots = []
    for hour in range(9, 17):
        for minute in [0, 30]:
            if hour == 16 and minute == 30:
                continue
            time_str = f"{hour:02d}:{minute:02d}"
            if db.check_slot_available(date_str, time_str):
                display_hour = hour if hour <= 12 else hour - 12
                am_pm = "AM" if hour < 12 else "PM"
                display_time = f"{display_hour}:{minute:02d} {am_pm}"
                slots.append({"time": time_str, "display": display_time})
    return slots


# ============================================================================
# TOOL FUNCTIONS - Using @llm.function_tool decorator
# ============================================================================

@llm.function_tool(description="Identify the user by their phone number. Call this when the user provides their phone number.")
async def identify_user(phone_number: str) -> str:
    """
    Identify user by phone number.
    
    Args:
        phone_number: The user's phone number, e.g., +1234567890
    """
    context.user_phone = phone_number
    
    user = db.get_user_by_phone(phone_number)
    if user:
        context.user_name = user.get("name")
        if context.user_name:
            return f"Welcome back, {context.user_name}! I found your account. How can I help you today?"
        return f"Welcome back! I found your account with phone number {phone_number}. How can I help you today?"
    else:
        db.create_user(phone_number)
        return f"I've registered your phone number {phone_number}. Welcome! How can I help you today?"


@llm.function_tool(description="Fetch available appointment slots for a specific date. The slots are 30 minutes each, from 9 AM to 5 PM.")
async def fetch_slots(date: str) -> str:
    """
    Get available appointment slots for a date.
    
    Args:
        date: The date to check slots for, in YYYY-MM-DD format
    """
    try:
        requested_date = datetime.strptime(date, "%Y-%m-%d").date()
        today = datetime.now().date()
        
        if requested_date < today:
            return "I'm sorry, I cannot book appointments in the past. Please choose a future date."
        
        slots = generate_available_slots(date)
        
        if not slots:
            return f"I'm sorry, there are no available slots on {date}. Would you like to check another date?"
        
        slot_list = ", ".join([s["display"] for s in slots[:8]])
        remaining = len(slots) - 8 if len(slots) > 8 else 0
        
        response = f"On {date}, the following slots are available: {slot_list}"
        if remaining > 0:
            response += f", and {remaining} more slots. Which time works best for you?"
        else:
            response += ". Which time works best for you?"
        
        return response
        
    except ValueError:
        return "I couldn't understand that date. Please provide a date in the format year-month-day, like 2024-01-20."


@llm.function_tool(description="Book an appointment for the user. The user must be identified first.")
async def book_appointment(date: str, time: str, description: str = "General appointment") -> str:
    """
    Book an appointment for the identified user.
    
    Args:
        date: The appointment date in YYYY-MM-DD format
        time: The appointment time in HH:MM format (24-hour)
        description: Brief description of the appointment purpose
    """
    if not context.user_phone:
        return "I need to identify you first. Could you please provide your phone number?"
    
    try:
        hour = int(time.split(":")[0])
        if hour < 9 or hour >= 17:
            return "I'm sorry, appointments are only available between 9 AM and 5 PM. Please choose a different time."
    except:
        return "I couldn't understand that time. Please provide a time like 10:00 or 14:30."
    
    result = db.book_appointment(
        user_phone=context.user_phone,
        date_str=date,
        time_str=time,
        description=description
    )
    
    if result["success"]:
        context.appointments_discussed.append({
            "action": "booked",
            "date": date,
            "time": time,
            "description": description
        })
        
        hour = int(time.split(":")[0])
        minute = time.split(":")[1]
        display_hour = hour if hour <= 12 else hour - 12
        am_pm = "AM" if hour < 12 else "PM"
        
        return f"I've booked your appointment for {date} at {display_hour}:{minute} {am_pm}. The purpose noted is: {description}. Is there anything else I can help you with?"
    else:
        return result["message"]


@llm.function_tool(description="Retrieve all appointments for the current user.")
async def retrieve_appointments() -> str:
    """Get all appointments for the identified user."""
    if not context.user_phone:
        return "I need to identify you first. Could you please provide your phone number?"
    
    appointments = db.get_user_appointments(context.user_phone)
    
    if not appointments:
        return "You don't have any appointments scheduled. Would you like to book one?"
    
    active = [a for a in appointments if a["status"] == "active"]
    
    if not active:
        return "You don't have any active appointments. Would you like to book one?"
    
    apt_list = []
    for apt in active[:5]:
        date = apt["date"]
        time = apt["time"]
        hour = int(time.split(":")[0])
        minute = time.split(":")[1]
        display_hour = hour if hour <= 12 else hour - 12
        am_pm = "AM" if hour < 12 else "PM"
        apt_list.append(f"{date} at {display_hour}:{minute} {am_pm}")
    
    response = f"You have {len(active)} active appointment(s). "
    response += "Here are your upcoming appointments: " + ", ".join(apt_list)
    
    if len(active) > 5:
        response += f", and {len(active) - 5} more."
    
    return response


@llm.function_tool(description="Cancel an existing appointment by its ID.")
async def cancel_appointment(appointment_id: str) -> str:
    """
    Cancel an appointment.
    
    Args:
        appointment_id: The unique ID of the appointment to cancel
    """
    result = db.cancel_appointment(appointment_id)
    
    if result["success"]:
        context.appointments_discussed.append({
            "action": "cancelled",
            "appointment_id": appointment_id
        })
        return "Your appointment has been cancelled successfully. Is there anything else I can help you with?"
    else:
        return result["message"]


@llm.function_tool(description="Modify an existing appointment's date and/or time.")
async def modify_appointment(appointment_id: str, new_date: str = "", new_time: str = "") -> str:
    """
    Modify an appointment's date or time.
    
    Args:
        appointment_id: The unique ID of the appointment to modify
        new_date: The new date in YYYY-MM-DD format (optional)
        new_time: The new time in HH:MM format (optional)
    """
    if not new_date and not new_time:
        return "Please specify a new date or time for the appointment."
    
    result = db.modify_appointment(appointment_id, new_date if new_date else None, new_time if new_time else None)
    
    if result["success"]:
        context.appointments_discussed.append({
            "action": "modified",
            "appointment_id": appointment_id,
            "new_date": new_date,
            "new_time": new_time
        })
        return result["message"] + " Is there anything else I can help you with?"
    else:
        return result["message"]


@llm.function_tool(description="End the conversation. Call this when the user indicates they want to end the call or says goodbye.")
async def end_conversation(user_preferences: str = "") -> str:
    """
    End the conversation and generate summary.
    
    Args:
        user_preferences: Any preferences or notes the user mentioned during the conversation
    """
    if user_preferences:
        context.preferences_mentioned.append(user_preferences)
    
    summary_parts = []
    
    if context.user_phone:
        summary_parts.append(f"User identified: {context.user_phone}")
    
    if context.appointments_discussed:
        summary_parts.append(f"Appointments discussed: {len(context.appointments_discussed)}")
        for apt in context.appointments_discussed:
            if apt["action"] == "booked":
                summary_parts.append(f"- Booked: {apt['date']} at {apt['time']} - {apt['description']}")
            elif apt["action"] == "cancelled":
                summary_parts.append(f"- Cancelled appointment: {apt['appointment_id']}")
            elif apt["action"] == "modified":
                summary_parts.append(f"- Modified appointment: {apt['appointment_id']}")
    
    if context.preferences_mentioned:
        summary_parts.append(f"User preferences: {', '.join(context.preferences_mentioned)}")
    
    summary = "\n".join(summary_parts) if summary_parts else "General inquiry - no appointments discussed."
    
    db.save_call_summary(
        user_phone=context.user_phone,
        summary=summary,
        appointments_discussed=context.appointments_discussed,
        preferences_mentioned=context.preferences_mentioned
    )
    
    context.reset()
    
    return "END_CALL"


# List of all tool functions for the agent
TOOLS = [
    identify_user,
    fetch_slots,
    book_appointment,
    retrieve_appointments,
    cancel_appointment,
    modify_appointment,
    end_conversation,
]
