-- ==============================================================================
-- Self-Learning ICP Tables for Supabase
-- ==============================================================================
-- Run this in Supabase SQL Editor to create the learning tables
-- Requires: pgvector extension (enable in Database → Extensions)
-- ==============================================================================

-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- ==============================================================================
-- ICP Learning Table
-- Stores deal outcomes with embeddings for pattern analysis
-- ==============================================================================
CREATE TABLE IF NOT EXISTS icp_learning (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    deal_id TEXT NOT NULL UNIQUE,
    contact_id TEXT,
    company_name TEXT,
    
    -- Features (stored as JSONB for flexibility)
    features JSONB DEFAULT '{}',
    
    -- Outcome tracking
    outcome TEXT NOT NULL CHECK (outcome IN ('won', 'lost', 'ghost', 'disqualified', 'pending')),
    outcome_reason TEXT,
    deal_value DECIMAL(12, 2) DEFAULT 0,
    days_to_close INTEGER,
    
    -- Vector embedding for similarity search (1536 dimensions for text-embedding-3-small)
    embedding vector(1536),
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    
    -- Indexes
    CONSTRAINT valid_outcome CHECK (outcome IS NOT NULL)
);

-- Create index on embedding for similarity search
CREATE INDEX IF NOT EXISTS icp_learning_embedding_idx 
ON icp_learning 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Create index on outcome for filtering
CREATE INDEX IF NOT EXISTS icp_learning_outcome_idx ON icp_learning(outcome);

-- Create index on created_at for time-based queries
CREATE INDEX IF NOT EXISTS icp_learning_created_idx ON icp_learning(created_at DESC);

-- ==============================================================================
-- ICP Weights Table
-- Stores learned weights for each trait
-- ==============================================================================
CREATE TABLE IF NOT EXISTS icp_weights (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    trait_key TEXT NOT NULL UNIQUE,
    trait_name TEXT NOT NULL,
    trait_value TEXT NOT NULL,
    
    -- Weight: positive = good ICP indicator, negative = bad
    weight DECIMAL(5, 4) DEFAULT 0.0 CHECK (weight >= -1 AND weight <= 1),
    
    -- Confidence: 0-1, increases with sample size
    confidence DECIMAL(4, 3) DEFAULT 0.1 CHECK (confidence >= 0 AND confidence <= 1),
    
    -- How many deals contributed to this weight
    sample_size INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on trait_key for fast lookups
CREATE INDEX IF NOT EXISTS icp_weights_key_idx ON icp_weights(trait_key);

-- ==============================================================================
-- ICP Analysis Reports Table
-- Stores weekly analysis reports
-- ==============================================================================
CREATE TABLE IF NOT EXISTS icp_reports (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    report_date DATE NOT NULL,
    report_type TEXT DEFAULT 'weekly',
    
    -- Report data
    total_deals INTEGER DEFAULT 0,
    win_rate DECIMAL(5, 2) DEFAULT 0,
    
    -- Patterns (stored as JSONB)
    winning_patterns JSONB DEFAULT '[]',
    losing_patterns JSONB DEFAULT '[]',
    
    -- Recommendations
    recommendations JSONB DEFAULT '[]',
    
    -- Full report
    full_report JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create unique index on report_date and type
CREATE UNIQUE INDEX IF NOT EXISTS icp_reports_date_type_idx ON icp_reports(report_date, report_type);

-- ==============================================================================
-- Helper Functions
-- ==============================================================================

-- Function to find similar won deals
CREATE OR REPLACE FUNCTION find_similar_won_deals(query_embedding vector(1536), match_count INT DEFAULT 5)
RETURNS TABLE (
    deal_id TEXT,
    company_name TEXT,
    similarity FLOAT,
    features JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        l.deal_id,
        l.company_name,
        1 - (l.embedding <=> query_embedding) as similarity,
        l.features
    FROM icp_learning l
    WHERE l.outcome = 'won'
    AND l.embedding IS NOT NULL
    ORDER BY l.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate current win rate
CREATE OR REPLACE FUNCTION get_win_rate(days_back INT DEFAULT 30)
RETURNS TABLE (
    total_deals BIGINT,
    won_deals BIGINT,
    win_rate DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*)::BIGINT as total_deals,
        COUNT(*) FILTER (WHERE outcome = 'won')::BIGINT as won_deals,
        COALESCE(
            COUNT(*) FILTER (WHERE outcome = 'won')::DECIMAL / NULLIF(COUNT(*), 0) * 100,
            0
        ) as win_rate
    FROM icp_learning
    WHERE created_at > NOW() - (days_back || ' days')::INTERVAL
    AND outcome IN ('won', 'lost');
END;
$$ LANGUAGE plpgsql;

-- ==============================================================================
-- Row Level Security (RLS) Policies
-- ==============================================================================

-- Enable RLS
ALTER TABLE icp_learning ENABLE ROW LEVEL SECURITY;
ALTER TABLE icp_weights ENABLE ROW LEVEL SECURITY;
ALTER TABLE icp_reports ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Service role has full access to icp_learning"
ON icp_learning FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role has full access to icp_weights"
ON icp_weights FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

CREATE POLICY "Service role has full access to icp_reports"
ON icp_reports FOR ALL
TO service_role
USING (true)
WITH CHECK (true);

-- Allow authenticated users to read
CREATE POLICY "Authenticated users can read icp_learning"
ON icp_learning FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "Authenticated users can read icp_weights"
ON icp_weights FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "Authenticated users can read icp_reports"
ON icp_reports FOR SELECT
TO authenticated
USING (true);

-- ==============================================================================
-- Comments
-- ==============================================================================
COMMENT ON TABLE icp_learning IS 'Stores deal outcomes with vector embeddings for ICP pattern learning';
COMMENT ON TABLE icp_weights IS 'Learned weights for ICP traits (positive = good, negative = bad)';
COMMENT ON TABLE icp_reports IS 'Weekly analysis reports with patterns and recommendations';
COMMENT ON FUNCTION find_similar_won_deals IS 'Find similar won deals using vector similarity search';
COMMENT ON FUNCTION get_win_rate IS 'Calculate win rate for the specified time period';

-- ==============================================================================
-- Done!
-- ==============================================================================
SELECT 'ICP Learning tables created successfully!' as status;
