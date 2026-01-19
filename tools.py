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
    import logging
    logger = logging.getLogger("voice-agent")
    
    # Normalize phone number - remove spaces, dashes, parentheses
    normalized_phone = phone_number.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    logger.info(f"identify_user called. Original: '{phone_number}', Normalized: '{normalized_phone}'")
    
    context.user_phone = normalized_phone
    
    user = db.get_user_by_phone(normalized_phone)
    if user:
        context.user_name = user.get("name")
        logger.info(f"Found existing user: {user}")
        if context.user_name:
            return f"Welcome back, {context.user_name}! I found your account. How can I help you today?"
        return f"Welcome back! I found your account with phone number {normalized_phone}. How can I help you today?"
    else:
        db.create_user(normalized_phone)
        logger.info(f"Created new user with phone: {normalized_phone}")
        return f"I've registered your phone number {normalized_phone}. Welcome! How can I help you today?"


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
        time: The appointment time (e.g., "2:00 PM", "14:00", "10:30 AM")
        description: Brief description of the appointment purpose
    """
    if not context.user_phone:
        return "I need to identify you first. Could you please provide your phone number?"
    
    # Parse time - handle both 12-hour ("2:00 PM") and 24-hour ("14:00") formats
    try:
        time_upper = time.upper().strip()
        
        if "AM" in time_upper or "PM" in time_upper:
            # 12-hour format: "2:00 PM", "10:30 AM"
            is_pm = "PM" in time_upper
            time_part = time_upper.replace("AM", "").replace("PM", "").strip()
            parts = time_part.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            
            # Convert to 24-hour
            if is_pm and hour != 12:
                hour += 12
            elif not is_pm and hour == 12:
                hour = 0
        else:
            # 24-hour format: "14:00"
            parts = time.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
        
        # Validate time is within business hours (9 AM - 5 PM)
        if hour < 9 or hour >= 17:
            return "I'm sorry, appointments are only available between 9 AM and 5 PM. Please choose a different time."
        
        # Format to 24-hour string for database
        time_24h = f"{hour:02d}:{minute:02d}"
        
    except Exception as e:
        return f"I couldn't understand that time format. Please provide a time like '10:00 AM' or '2:30 PM'."
    
    result = db.book_appointment(
        user_phone=context.user_phone,
        date_str=date,
        time_str=time_24h,
        description=description
    )
    
    if result["success"]:
        context.appointments_discussed.append({
            "action": "booked",
            "date": date,
            "time": time_24h,
            "description": description
        })
        
        # Format display time
        display_hour = hour if hour <= 12 else hour - 12
        if display_hour == 0:
            display_hour = 12
        am_pm = "AM" if hour < 12 else "PM"
        
        return f"I've booked your appointment for {date} at {display_hour}:{minute:02d} {am_pm}. The purpose noted is: {description}. Is there anything else I can help you with?"
    else:
        return result["message"]


@llm.function_tool(description="Retrieve all appointments for the current user.")
async def retrieve_appointments(placeholder: str = "") -> str:
    """Get all appointments for the identified user.
    
    Args:
        placeholder: Unused placeholder parameter for API compatibility.
    """
    import logging
    logger = logging.getLogger("voice-agent")
    
    logger.info(f"retrieve_appointments called. context.user_phone = {context.user_phone}")
    
    if not context.user_phone:
        return "I need to identify you first. Could you please provide your phone number?"
    
    appointments = db.get_user_appointments(context.user_phone)
    
    logger.info(f"Found {len(appointments) if appointments else 0} appointments for {context.user_phone}")
    logger.info(f"Appointments data: {appointments}")
    
    if not appointments:
        return "You don't have any appointments scheduled. Would you like to book one?"
    
    # Treat null/missing status as "active" (for backwards compatibility)
    active = [a for a in appointments if a.get("status") in ("active", None) or a.get("status") == ""]
    
    logger.info(f"Active appointments after filtering: {len(active)}")
    
    if not active:
        return "You don't have any active appointments. Would you like to book one?"
    
    apt_list = []
    for i, apt in enumerate(active[:5], 1):
        date = apt["date"]
        time = apt["time"]
        apt_id = apt.get("id", "unknown")
        hour = int(time.split(":")[0])
        minute = time.split(":")[1]
        display_hour = hour if hour <= 12 else hour - 12
        if display_hour == 0:
            display_hour = 12
        am_pm = "AM" if hour < 12 else "PM"
        # Include ID in a natural way for the LLM to reference
        apt_list.append(f"Appointment {i} (ID: {apt_id}): {date} at {display_hour}:{minute} {am_pm}")
    
    response = f"You have {len(active)} active appointment(s). "
    response += "Here are your appointments: " + "; ".join(apt_list)
    response += ". To cancel or modify, use the appointment ID."
    
    if len(active) > 5:
        response += f" You also have {len(active) - 5} more appointments not shown."
    
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
