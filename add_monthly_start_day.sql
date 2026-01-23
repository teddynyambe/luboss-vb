-- Add monthly_start_day column to cycle_phase table
-- Run this SQL directly in your PostgreSQL database

ALTER TABLE cycle_phase 
ADD COLUMN IF NOT EXISTS monthly_start_day INTEGER;
