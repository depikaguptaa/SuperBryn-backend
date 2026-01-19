-- Supabase Database Schema for Voice Agent Appointment Booking
-- Run this SQL in your Supabase SQL Editor to create the required tables

-- ============================================================================
-- USERS TABLE
-- ============================================================================
-- Stores user information, indexed by phone number
CREATE TABLE IF NOT EXISTS users (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    phone_number TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fast phone lookups
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone_number);

-- ============================================================================
-- APPOINTMENTS TABLE
-- ============================================================================
-- Stores all appointment bookings
CREATE TABLE IF NOT EXISTS appointments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_phone TEXT NOT NULL,
    date TEXT NOT NULL,  -- Format: YYYY-MM-DD
    time TEXT NOT NULL,  -- Format: HH:MM (24-hour)
    description TEXT DEFAULT 'General appointment',
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'completed')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_appointments_user ON appointments(user_phone);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(date);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);

-- Unique constraint to prevent double-booking (only for active appointments)
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_booking 
ON appointments(date, time) 
WHERE status = 'active';

-- ============================================================================
-- CALL SUMMARIES TABLE
-- ============================================================================
-- Stores summaries of voice conversations
CREATE TABLE IF NOT EXISTS call_summaries (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_phone TEXT,
    summary TEXT,
    appointments_discussed JSONB DEFAULT '[]',
    preferences_mentioned JSONB DEFAULT '[]',
    cost_breakdown JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for user lookup
CREATE INDEX IF NOT EXISTS idx_call_summaries_user ON call_summaries(user_phone);

-- ============================================================================
-- ROW LEVEL SECURITY (RLS) - Optional but Recommended
-- ============================================================================
-- Enable RLS on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_summaries ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (for backend API)
CREATE POLICY "Service role has full access to users" ON users
    FOR ALL USING (true);

CREATE POLICY "Service role has full access to appointments" ON appointments
    FOR ALL USING (true);

CREATE POLICY "Service role has full access to call_summaries" ON call_summaries
    FOR ALL USING (true);
