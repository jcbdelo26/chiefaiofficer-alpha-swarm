-- Supabase Schema for Revenue Swarm
-- Unified data layer replacing file-based .hive-mind storage

-- Enable pgvector extension for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- LEADS TABLE
-- Replaces: .hive-mind/scraped/, enriched/, segmented/
-- Central repository for all lead data throughout the pipeline
-- ============================================================================
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Core identification
    email TEXT UNIQUE,
    company_name TEXT,
    company_domain TEXT,
    
    -- Contact info
    first_name TEXT,
    last_name TEXT,
    title TEXT,
    phone TEXT,
    linkedin_url TEXT,
    
    -- Company data
    industry TEXT,
    employee_count INTEGER,
    revenue_range TEXT,
    location TEXT,
    timezone TEXT,
    
    -- Enrichment data (from enrichment agent)
    enrichment_data JSONB DEFAULT '{}',
    tech_stack TEXT[],
    pain_points TEXT[],
    
    -- Segmentation (from segmentation agent)
    segment TEXT,
    segment_confidence FLOAT,
    icp_score FLOAT,
    
    -- Embeddings for vector search
    embedding vector(1536),
    
    -- Pipeline tracking
    source TEXT,
    source_url TEXT,
    scraped_at TIMESTAMPTZ,
    enriched_at TIMESTAMPTZ,
    segmented_at TIMESTAMPTZ,
    
    -- Status
    status TEXT DEFAULT 'raw' CHECK (status IN ('raw', 'enriched', 'segmented', 'contacted', 'converted', 'rejected')),
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_leads_email ON leads(email);
CREATE INDEX idx_leads_segment ON leads(segment);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_icp_score ON leads(icp_score DESC);
CREATE INDEX idx_leads_embedding ON leads USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================================
-- OUTCOMES TABLE
-- Campaign outcomes for self-annealing feedback loops
-- ============================================================================
CREATE TABLE IF NOT EXISTS outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- References
    campaign_id UUID REFERENCES campaigns(id),
    lead_id UUID REFERENCES leads(id),
    
    -- Outcome data
    action_taken TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('success', 'failure', 'pending', 'partial')),
    
    -- Metrics
    open_rate FLOAT,
    click_rate FLOAT,
    reply_rate FLOAT,
    conversion_rate FLOAT,
    
    -- Context for learning
    segment TEXT,
    template_used TEXT,
    channel TEXT,
    send_time TIMESTAMPTZ,
    
    -- Feedback
    feedback_text TEXT,
    feedback_sentiment FLOAT,
    
    -- For RL training
    state_vector JSONB,
    reward FLOAT,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_outcomes_campaign ON outcomes(campaign_id);
CREATE INDEX idx_outcomes_lead ON outcomes(lead_id);
CREATE INDEX idx_outcomes_result ON outcomes(result);
CREATE INDEX idx_outcomes_segment ON outcomes(segment);

-- ============================================================================
-- Q_TABLE
-- RL Q-values for state-action pairs (self-annealing memory)
-- ============================================================================
CREATE TABLE IF NOT EXISTS q_table (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- State-action pair
    state_hash TEXT NOT NULL,
    state_description JSONB NOT NULL,
    action TEXT NOT NULL,
    
    -- Q-value and stats
    q_value FLOAT DEFAULT 0.0,
    visit_count INTEGER DEFAULT 0,
    last_reward FLOAT,
    avg_reward FLOAT DEFAULT 0.0,
    
    -- Exploration tracking
    exploration_bonus FLOAT DEFAULT 0.0,
    last_visited TIMESTAMPTZ,
    
    -- Context
    segment TEXT,
    channel TEXT,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(state_hash, action)
);

CREATE INDEX idx_qtable_state ON q_table(state_hash);
CREATE INDEX idx_qtable_action ON q_table(action);
CREATE INDEX idx_qtable_qvalue ON q_table(q_value DESC);
CREATE INDEX idx_qtable_segment ON q_table(segment);

-- ============================================================================
-- CAMPAIGNS TABLE
-- Generated campaigns and their configurations
-- ============================================================================
CREATE TABLE IF NOT EXISTS campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Campaign identity
    name TEXT NOT NULL,
    description TEXT,
    
    -- Targeting
    target_segment TEXT,
    target_criteria JSONB,
    
    -- Content
    template_id TEXT,
    subject_line TEXT,
    body_template TEXT,
    cta TEXT,
    
    -- Channel and timing
    channel TEXT CHECK (channel IN ('email', 'linkedin', 'phone', 'multi')),
    scheduled_at TIMESTAMPTZ,
    
    -- Configuration
    config JSONB DEFAULT '{}',
    personalization_rules JSONB DEFAULT '[]',
    
    -- Performance
    status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'scheduled', 'running', 'paused', 'completed', 'failed')),
    leads_count INTEGER DEFAULT 0,
    sent_count INTEGER DEFAULT 0,
    
    -- Aggregated metrics
    total_opens INTEGER DEFAULT 0,
    total_clicks INTEGER DEFAULT 0,
    total_replies INTEGER DEFAULT 0,
    total_conversions INTEGER DEFAULT 0,
    
    -- Self-annealing reference
    parent_campaign_id UUID REFERENCES campaigns(id),
    iteration INTEGER DEFAULT 1,
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_campaigns_status ON campaigns(status);
CREATE INDEX idx_campaigns_segment ON campaigns(target_segment);
CREATE INDEX idx_campaigns_channel ON campaigns(channel);
CREATE INDEX idx_campaigns_created ON campaigns(created_at DESC);

-- ============================================================================
-- PATTERNS TABLE
-- Detected success/failure patterns from outcomes
-- ============================================================================
CREATE TABLE IF NOT EXISTS patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Pattern identification
    pattern_type TEXT NOT NULL CHECK (pattern_type IN ('success', 'failure', 'anomaly', 'trend')),
    pattern_name TEXT NOT NULL,
    description TEXT,
    
    -- Pattern definition
    conditions JSONB NOT NULL,
    confidence FLOAT NOT NULL,
    support_count INTEGER DEFAULT 1,
    
    -- Context
    segment TEXT,
    channel TEXT,
    time_range TSTZRANGE,
    
    -- Impact metrics
    avg_conversion_lift FLOAT,
    avg_engagement_lift FLOAT,
    
    -- Recommendations
    recommended_actions JSONB DEFAULT '[]',
    
    -- Validation
    validated BOOLEAN DEFAULT FALSE,
    validated_at TIMESTAMPTZ,
    validation_notes TEXT,
    
    -- Embedding for similarity search
    embedding vector(1536),
    
    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    discovered_by TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_patterns_type ON patterns(pattern_type);
CREATE INDEX idx_patterns_segment ON patterns(segment);
CREATE INDEX idx_patterns_confidence ON patterns(confidence DESC);
CREATE INDEX idx_patterns_embedding ON patterns USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- ============================================================================
-- AUDIT_LOG TABLE
-- All operations for compliance and debugging
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Operation details
    operation TEXT NOT NULL,
    table_name TEXT,
    record_id UUID,
    
    -- Actor
    agent_id TEXT,
    agent_type TEXT,
    user_id TEXT,
    
    -- Request context
    request_id TEXT,
    session_id TEXT,
    
    -- Data
    details JSONB DEFAULT '{}',
    old_values JSONB,
    new_values JSONB,
    
    -- Status
    status TEXT DEFAULT 'success' CHECK (status IN ('success', 'failure', 'pending')),
    error_message TEXT,
    
    -- Timing
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    duration_ms INTEGER,
    
    -- Compliance
    ip_address TEXT,
    user_agent TEXT,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_audit_operation ON audit_log(operation);
CREATE INDEX idx_audit_table ON audit_log(table_name);
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_agent ON audit_log(agent_id);
CREATE INDEX idx_audit_status ON audit_log(status);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Function to get all tables (used by list_tables)
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

-- Vector similarity search function
CREATE OR REPLACE FUNCTION match_vectors(
    query_embedding vector(1536),
    match_threshold FLOAT,
    match_count INT,
    table_name TEXT,
    embedding_column TEXT,
    filter_column TEXT DEFAULT NULL,
    filter_value TEXT DEFAULT NULL
)
RETURNS TABLE(
    id UUID,
    similarity FLOAT,
    data JSONB
) AS $$
DECLARE
    query TEXT;
BEGIN
    query := format(
        'SELECT id, 1 - (%I <=> $1) as similarity, to_jsonb(t.*) as data
         FROM %I t
         WHERE 1 - (%I <=> $1) > $2',
        embedding_column, table_name, embedding_column
    );
    
    IF filter_column IS NOT NULL AND filter_value IS NOT NULL THEN
        query := query || format(' AND %I = $4', filter_column);
    END IF;
    
    query := query || ' ORDER BY similarity DESC LIMIT $3';
    
    IF filter_column IS NOT NULL THEN
        RETURN QUERY EXECUTE query USING query_embedding, match_threshold, match_count, filter_value;
    ELSE
        RETURN QUERY EXECUTE query USING query_embedding, match_threshold, match_count;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply update trigger to relevant tables
CREATE TRIGGER update_leads_timestamp
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_qtable_timestamp
    BEFORE UPDATE ON q_table
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_campaigns_timestamp
    BEFORE UPDATE ON campaigns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_patterns_timestamp
    BEFORE UPDATE ON patterns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- ROW LEVEL SECURITY (Optional - enable for multi-tenant)
-- ============================================================================
-- ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE outcomes ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE campaigns ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE patterns ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- GRANTS
-- ============================================================================
-- GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
-- GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO service_role;
