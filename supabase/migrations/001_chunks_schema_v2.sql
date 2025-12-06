-- ============================================================
-- SWOOPINFO CHUNKS TABLE SCHEMA v2.0
-- ============================================================
-- This migration creates or updates the chunks table to support
-- the bulletproof deterministic architecture.
--
-- Content ID Format: {chunk_type}:{component}
-- Vehicle Key Format: {year}_{make}_{model}_{engine}
--
-- Run this in Supabase SQL Editor
-- ============================================================

-- ============================================================
-- STEP 1: Create chunks table if not exists
-- ============================================================
CREATE TABLE IF NOT EXISTS chunks (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  
  -- IDENTITY (immutable after creation)
  vehicle_key text NOT NULL,           -- e.g. "2019_honda_accord_2.0t"
  content_id text NOT NULL,            -- e.g. "fluid_capacity:engine_oil"
  chunk_type text NOT NULL,            -- e.g. "fluid_capacity", "torque_spec"
  
  -- CONTENT
  title text,                          -- Human-readable title
  content_text text,                   -- Plain text content
  data jsonb DEFAULT '{}'::jsonb,      -- Structured data (varies by chunk_type)
  
  -- SOURCES
  sources text[] DEFAULT ARRAY[]::text[],  -- Source citations
  source_confidence real DEFAULT 0.0,      -- 0.0 to 1.0
  
  -- VERIFICATION PIPELINE
  verification_status text DEFAULT 'pending_verification',  -- pending_verification, verified, rejected
  qa_status text DEFAULT 'pending',                         -- pending, pass, fail
  qa_notes text,                                            -- Notes from QA process
  qa_pass_count integer DEFAULT 0,                          -- Number of times passed QA
  last_qa_reviewed_at timestamptz,                          -- When last reviewed
  
  -- TRUST LEVELS (Stage 5 Confidence Promotion)
  verified_status text DEFAULT 'unverified',  -- unverified, candidate, verified, banned
  verified_at timestamptz,                     -- When promoted to verified
  failed_at timestamptz,                       -- When marked as failed
  promotion_count integer DEFAULT 0,           -- How many times promoted
  
  -- REPAIR TRACKING
  regeneration_attempts integer DEFAULT 0,     -- Number of repair attempts
  regenerated_at timestamptz,                  -- Last regeneration timestamp
  
  -- METADATA
  template_type text,                          -- Optional template identifier
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now(),
  
  -- UNIQUE CONSTRAINT: One chunk per vehicle+content_id+chunk_type
  CONSTRAINT chunks_unique_key UNIQUE (vehicle_key, content_id, chunk_type)
);

-- ============================================================
-- STEP 2: Add missing columns to existing table
-- ============================================================
-- These will silently succeed if columns already exist

DO $$ 
BEGIN
  -- qa_pass_count
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                 WHERE table_name = 'chunks' AND column_name = 'qa_pass_count') THEN
    ALTER TABLE chunks ADD COLUMN qa_pass_count integer DEFAULT 0;
  END IF;
  
  -- verified_status
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                 WHERE table_name = 'chunks' AND column_name = 'verified_status') THEN
    ALTER TABLE chunks ADD COLUMN verified_status text DEFAULT 'unverified';
  END IF;
  
  -- verified_at
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                 WHERE table_name = 'chunks' AND column_name = 'verified_at') THEN
    ALTER TABLE chunks ADD COLUMN verified_at timestamptz;
  END IF;
  
  -- failed_at
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                 WHERE table_name = 'chunks' AND column_name = 'failed_at') THEN
    ALTER TABLE chunks ADD COLUMN failed_at timestamptz;
  END IF;
  
  -- promotion_count
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                 WHERE table_name = 'chunks' AND column_name = 'promotion_count') THEN
    ALTER TABLE chunks ADD COLUMN promotion_count integer DEFAULT 0;
  END IF;
  
  -- sources (change from text to text[])
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                 WHERE table_name = 'chunks' AND column_name = 'sources') THEN
    ALTER TABLE chunks ADD COLUMN sources text[] DEFAULT ARRAY[]::text[];
  END IF;
END $$;

-- ============================================================
-- STEP 3: Create indexes for performance
-- ============================================================
-- Drop old indexes if they exist (with different names)
DROP INDEX IF EXISTS idx_chunks_vehicle;
DROP INDEX IF EXISTS idx_chunks_type;
DROP INDEX IF EXISTS idx_chunks_qa;
DROP INDEX IF EXISTS idx_chunks_verified;

-- Create optimized indexes
CREATE INDEX IF NOT EXISTS idx_chunks_vehicle_key ON chunks(vehicle_key);
CREATE INDEX IF NOT EXISTS idx_chunks_content_id ON chunks(content_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chunk_type ON chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_qa_status ON chunks(qa_status);
CREATE INDEX IF NOT EXISTS idx_chunks_verified_status ON chunks(verified_status);

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS idx_chunks_vehicle_type ON chunks(vehicle_key, chunk_type);
CREATE INDEX IF NOT EXISTS idx_chunks_vehicle_content ON chunks(vehicle_key, content_id);

-- Index for pending QA (common query)
CREATE INDEX IF NOT EXISTS idx_chunks_pending_qa ON chunks(qa_status) WHERE qa_status = 'pending';

-- ============================================================
-- STEP 4: Create updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION update_chunks_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS chunks_updated_at ON chunks;
CREATE TRIGGER chunks_updated_at
  BEFORE UPDATE ON chunks
  FOR EACH ROW
  EXECUTE FUNCTION update_chunks_updated_at();

-- ============================================================
-- STEP 5: Row Level Security
-- ============================================================
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;

-- Allow all operations (SwoopInfo uses service role key)
DROP POLICY IF EXISTS "Allow all chunks access" ON chunks;
CREATE POLICY "Allow all chunks access" ON chunks FOR ALL USING (true);

-- ============================================================
-- STEP 6: Create supporting tables
-- ============================================================

-- QA History Table (for daily QA runs)
-- Drop and recreate if schema changed
DO $$
BEGIN
  -- Check if table exists with wrong schema
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'qa_history_daily') THEN
    -- Check if run_date column exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'qa_history_daily' AND column_name = 'run_date') THEN
      -- Add missing column
      ALTER TABLE qa_history_daily ADD COLUMN IF NOT EXISTS run_date date DEFAULT CURRENT_DATE;
    END IF;
  ELSE
    -- Create table fresh
    CREATE TABLE qa_history_daily (
      id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
      run_date date NOT NULL DEFAULT CURRENT_DATE,
      total_chunks integer DEFAULT 0,
      passed integer DEFAULT 0,
      failed integer DEFAULT 0,
      repaired integer DEFAULT 0,
      duration_ms integer,
      notes text,
      created_at timestamptz DEFAULT now()
    );
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_qa_history_date ON qa_history_daily(run_date);

-- Enable RLS
ALTER TABLE qa_history_daily ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all qa_history access" ON qa_history_daily;
CREATE POLICY "Allow all qa_history access" ON qa_history_daily FOR ALL USING (true);

-- ============================================================
-- STEP 7: Create vehicles registry table
-- ============================================================
-- This tracks which vehicles have been onboarded/populated
CREATE TABLE IF NOT EXISTS swoopinfo_vehicles (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  vehicle_key text UNIQUE NOT NULL,     -- e.g. "2019_honda_accord_2.0t"
  year integer NOT NULL,
  make text NOT NULL,
  model text NOT NULL,
  engine text,                           -- e.g. "2.0t", "3.5l_v6"
  
  -- Onboarding status
  status text DEFAULT 'pending',         -- pending, in_progress, complete
  chunks_total integer DEFAULT 0,        -- Total chunks for this vehicle
  chunks_verified integer DEFAULT 0,     -- Verified chunks count
  
  -- Metadata
  source text,                           -- How it was added (booking, manual, import)
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_swoopinfo_vehicles_key ON swoopinfo_vehicles(vehicle_key);
CREATE INDEX IF NOT EXISTS idx_swoopinfo_vehicles_status ON swoopinfo_vehicles(status);
CREATE INDEX IF NOT EXISTS idx_swoopinfo_vehicles_make ON swoopinfo_vehicles(make);

-- Enable RLS
ALTER TABLE swoopinfo_vehicles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow all swoopinfo_vehicles access" ON swoopinfo_vehicles;
CREATE POLICY "Allow all swoopinfo_vehicles access" ON swoopinfo_vehicles FOR ALL USING (true);

-- Updated_at trigger
DROP TRIGGER IF EXISTS swoopinfo_vehicles_updated_at ON swoopinfo_vehicles;
CREATE TRIGGER swoopinfo_vehicles_updated_at
  BEFORE UPDATE ON swoopinfo_vehicles
  FOR EACH ROW
  EXECUTE FUNCTION update_chunks_updated_at();

-- ============================================================
-- STEP 8: Cleanup - Remove unused columns (if any)
-- ============================================================
-- Comment out lines to preserve columns if needed

-- These columns are deprecated/unused:
-- ALTER TABLE chunks DROP COLUMN IF EXISTS old_column_name;

-- ============================================================
-- STEP 9: Verify schema
-- ============================================================
-- Run this query to verify the schema is correct:
/*
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'chunks'
ORDER BY ordinal_position;
*/

-- ============================================================
-- MIGRATION COMPLETE
-- ============================================================
-- Expected columns in chunks table:
-- id (uuid), vehicle_key (text), content_id (text), chunk_type (text),
-- title (text), content_text (text), data (jsonb), sources (text[]),
-- source_confidence (real), verification_status (text), qa_status (text),
-- qa_notes (text), qa_pass_count (int), last_qa_reviewed_at (timestamptz),
-- verified_status (text), verified_at (timestamptz), failed_at (timestamptz),
-- promotion_count (int), regeneration_attempts (int), regenerated_at (timestamptz),
-- template_type (text), created_at (timestamptz), updated_at (timestamptz)
