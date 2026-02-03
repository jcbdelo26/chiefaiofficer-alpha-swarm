-- Supabase Schema for Revenue Swarm (ORDERED VERSION)
-- Run this in Supabase SQL Editor
-- Tables ordered to respect foreign key dependencies

-- Enable pgvector extension for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- 1. LEADS TABLE (No dependencies)
-- ============================================================================
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE,
    company_name TEXT,
    company_domain TEXT,
    first_name TEXT,
    last_name TEXT,
    title TEXT,
    phone TEXT,
    linkedin_url TEXT,
    industry TEXT,
    employee_count INTEGER,
    revenue_range TEXT,
    location TEXT,
    timezone TEXT,
    enrichment_data JSONB DEFAULT '{}',
    tech_stack TEXT[],
    pain_points TEXT[],
    segment TEXT,
    segment_confidence FLOAT,
    icp_score FLOAT,
    embedding vector(1536),
    source TEXT,
    source_url TEXT,
    scraped_at TIMESTAMPTZ,
    enriched_at TIMESTAMPTZ,
    segmented_at TIMESTAMPTZ,
    status TEXT DEFAULT 'raw' CHECK (status IN ('raw', 'enriched', 'segmented', 'contacted', 'converted', 'rejected')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- ============================================================================
-- 2. CAMPAIGNS TABLE (No dependencies, self-reference for parent)
-- ============================================================================
CREATE TABLE IF NOT EXISTS campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    target_segment TEXT,
    target_criteria JSONB,
    template_id TEXT,
    subject_line TEXT,
    body_template TEXT,
    cta TEXT,
    channel TEXT CHECK (channel IN ('email', 'linkedin', 'phone', 'multi')),
    scheduled_at TIMESTAMPTZ,
    config JSONB DEFAULT '{}',
    personalization_rules JSONB DEFAULT '[]',
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'scheduled', 'running', 'paused', 'completed', 'failed')),
    leads_count INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    total_opens INTEGER DEFAULT 0,
    total_clicks INTEGER DEFAULT 0,
    total_replies INTEGER DEFAULT 0,
    total_conversions INTEGER DEFAULT 0,
    parent_campaign_id UUID REFERENCES campaigns(id),
    iteration INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,
    metadata JSONB DEFAULT '{}'
);

-- ============================================================================
-- 3. OUTCOMES TABLE (Depends on campaigns and leads)
-- ============================================================================
CREATE TABLE IF NOT EXISTS outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES campaigns(id),
    lead_id UUID REFERENCES leads(id),
    action_taken TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('success', 'failure', 'pending', 'partial')),
    open_rate FLOAT,
    click_rate FLOAT,
    reply_rate FLOAT,
    conversion_rate FLOAT,
    segment TEXT,
    template_used TEXT,
    channel TEXT,
    send_time TIMESTAMPTZ,
    feedback_text TEXT,
    feedback_sentiment FLOAT,
    state_vector JSONB,
    reward FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- ============================================================================
-- 4. Q_TABLE (No dependencies)
-- ============================================================================
CREATE TABLE IF NOT EXISTS q_table (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_hash TEXT NOT NULL,
    state_description JSONB NOT NULL,
    action TEXT NOT NULL,
    q_value FLOAT DEFAULT 0.0,
    visit_count INTEGER DEFAULT 0,
    last_reward FLOAT,
    avg_reward FLOAT DEFAULT 0.0,
    exploration_bonus FLOAT DEFAULT 0.0,
    last_visited TIMESTAMPTZ,
    segment TEXT,
    channel TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(state_hash, action)
);

-- ============================================================================
-- 5. PATTERNS TABLE (No dependencies)
-- ============================================================================
CREATE TABLE IF NOT EXISTS patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_type TEXT NOT NULL CHECK (pattern_type IN ('success', 'failure', 'anomaly', 'trend')),
    pattern_name TEXT NOT NULL,
    description TEXT,
    conditions JSONB NOT NULL,
    confidence FLOAT NOT NULL,
    support_count INTEGER DEFAULT 1,
    segment TEXT,
    channel TEXT,
    time_range TSTZRANGE,
    avg_conversion_lift FLOAT,
    avg_engagement_lift FLOAT,
    recommended_actions JSONB DEFAULT '[]',
    validated BOOLEAN DEFAULT FALSE,
    validated_at TIMESTAMPTZ,
    validation_notes TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    discovered_by TEXT,
    metadata JSONB DEFAULT '{}'
);

-- ============================================================================
-- 6. AUDIT_LOG TABLE (No dependencies)
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation TEXT NOT NULL,
    table_name TEXT,
    record_id UUID,
    agent_id TEXT,
    agent_type TEXT,
    user_id TEXT,
    request_id TEXT,
    session_id TEXT,
    details JSONB DEFAULT '{}',
    old_values JSONB,
    new_values JSONB,
    status TEXT DEFAULT 'success' CHECK (status IN ('success', 'failure', 'pending')),
    error_message TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    duration_ms INTEGER,
    ip_address TEXT,
    user_agent TEXT,
    metadata JSONB DEFAULT '{}'
);

-- ============================================================================
-- INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_leads_segment ON leads(segment);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_icp_score ON leads(icp_score DESC);

CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_segment ON campaigns(target_segment);
CREATE INDEX IF NOT EXISTS idx_campaigns_channel ON campaigns(channel);
CREATE INDEX IF NOT EXISTS idx_campaigns_created ON campaigns(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_outcomes_campaign ON outcomes(campaign_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_lead ON outcomes(lead_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_result ON outcomes(result);
CREATE INDEX IF NOT EXISTS idx_outcomes_segment ON outcomes(segment);

CREATE INDEX IF NOT EXISTS idx_qtable_state ON q_table(state_hash);
CREATE INDEX IF NOT EXISTS idx_qtable_action ON q_table(action);
CREATE INDEX IF NOT EXISTS idx_qtable_qvalue ON q_table(q_value DESC);
CREATE INDEX IF NOT EXISTS idx_qtable_segment ON q_table(segment);

CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_patterns_segment ON patterns(segment);
CREATE INDEX IF NOT EXISTS idx_patterns_confidence ON patterns(confidence DESC);

CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_log(operation);
CREATE INDEX IF NOT EXISTS idx_audit_table ON audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_audit_status ON audit_log(status);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================
CREATE OR REPLACE FUNCTION get_tables()
RETURNS TABLE(table_name TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT t.table_name::TEXT
    FROM information_schema.tables t
    WHERE t.table_schema = 'public'
    AND t.table_type = 'BASE TABLE';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- TRIGGERS
-- ============================================================================
DROP TRIGGER IF EXISTS update_leads_timestamp ON leads;
CREATE TRIGGER update_leads_timestamp
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_qtable_timestamp ON q_table;
CREATE TRIGGER update_qtable_timestamp
    BEFORE UPDATE ON q_table
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_campaigns_timestamp ON campaigns;
CREATE TRIGGER update_campaigns_timestamp
    BEFORE UPDATE ON campaigns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_patterns_timestamp ON patterns;
CREATE TRIGGER update_patterns_timestamp
    BEFORE UPDATE ON patterns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- DONE!
-- ============================================================================
-- Verify with: SELECT * FROM get_tables();
