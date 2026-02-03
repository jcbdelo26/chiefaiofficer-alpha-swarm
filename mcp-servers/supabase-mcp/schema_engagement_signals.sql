-- Engagement Signals Table for Lead Router
-- Run this AFTER schema_ordered.sql in Supabase SQL Editor
-- Tracks all engagement signals for context-aware routing

-- ============================================================================
-- ENGAGEMENT_SIGNALS TABLE (Depends on leads)
-- ============================================================================
CREATE TABLE IF NOT EXISTS engagement_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    email TEXT,
    
    -- Email engagement signals
    emails_sent INTEGER DEFAULT 0,
    emails_opened INTEGER DEFAULT 0,
    emails_clicked INTEGER DEFAULT 0,
    emails_replied INTEGER DEFAULT 0,
    emails_bounced INTEGER DEFAULT 0,
    last_email_sent TIMESTAMPTZ,
    last_email_open TIMESTAMPTZ,
    last_email_click TIMESTAMPTZ,
    last_email_reply TIMESTAMPTZ,
    
    -- LinkedIn engagement signals
    linkedin_connected BOOLEAN DEFAULT FALSE,
    linkedin_connection_date TIMESTAMPTZ,
    linkedin_messages_sent INTEGER DEFAULT 0,
    linkedin_messages_received INTEGER DEFAULT 0,
    linkedin_profile_viewed BOOLEAN DEFAULT FALSE,
    linkedin_post_engaged BOOLEAN DEFAULT FALSE,
    last_linkedin_activity TIMESTAMPTZ,
    
    -- Website/Intent signals
    website_visits INTEGER DEFAULT 0,
    pages_viewed TEXT[] DEFAULT '{}',
    time_on_site_seconds INTEGER DEFAULT 0,
    rb2b_identified BOOLEAN DEFAULT FALSE,
    rb2b_identified_at TIMESTAMPTZ,
    last_website_visit TIMESTAMPTZ,
    
    -- CRM/Pipeline signals
    in_crm BOOLEAN DEFAULT FALSE,
    crm_contact_id TEXT,
    crm_stage TEXT,
    meetings_booked INTEGER DEFAULT 0,
    meetings_completed INTEGER DEFAULT 0,
    meetings_no_show INTEGER DEFAULT 0,
    forms_submitted INTEGER DEFAULT 0,
    last_crm_activity TIMESTAMPTZ,
    
    -- Inbound/Intent signals
    inbound_source TEXT,
    requested_contact BOOLEAN DEFAULT FALSE,
    requested_contact_at TIMESTAMPTZ,
    downloaded_content BOOLEAN DEFAULT FALSE,
    content_downloaded TEXT[],
    pricing_page_viewed BOOLEAN DEFAULT FALSE,
    demo_page_viewed BOOLEAN DEFAULT FALSE,
    
    -- Routing state
    current_platform TEXT CHECK (current_platform IN ('instantly', 'gohighlevel', 'hybrid', 'none')),
    engagement_score FLOAT DEFAULT 0.0,
    engagement_level TEXT CHECK (engagement_level IN ('cold', 'lukewarm', 'warm', 'hot')),
    last_routing_decision JSONB,
    last_routed_at TIMESTAMPTZ,
    transition_count INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Ensure one record per lead
    UNIQUE(lead_id),
    UNIQUE(email)
);

-- ============================================================================
-- ENGAGEMENT_EVENTS TABLE (Event log for signals)
-- ============================================================================
CREATE TABLE IF NOT EXISTS engagement_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    signal_id UUID REFERENCES engagement_signals(id) ON DELETE CASCADE,
    
    event_type TEXT NOT NULL CHECK (event_type IN (
        'email_sent', 'email_opened', 'email_clicked', 'email_replied', 'email_bounced',
        'linkedin_connected', 'linkedin_message_sent', 'linkedin_message_received',
        'website_visit', 'page_view', 'rb2b_identified',
        'form_submitted', 'content_downloaded', 'meeting_booked', 'meeting_completed',
        'pipeline_stage_changed', 'platform_transition'
    )),
    
    event_source TEXT CHECK (event_source IN ('instantly', 'gohighlevel', 'linkedin', 'rb2b', 'website', 'manual')),
    event_data JSONB DEFAULT '{}',
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- PLATFORM_TRANSITIONS TABLE (Track lead movements between platforms)
-- ============================================================================
CREATE TABLE IF NOT EXISTS platform_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    
    from_platform TEXT CHECK (from_platform IN ('instantly', 'gohighlevel', 'none')),
    to_platform TEXT NOT NULL CHECK (to_platform IN ('instantly', 'gohighlevel')),
    
    trigger_event TEXT NOT NULL,
    trigger_data JSONB DEFAULT '{}',
    
    engagement_score_at_transition FLOAT,
    engagement_level_at_transition TEXT,
    
    routing_decision JSONB,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_signals_lead ON engagement_signals(lead_id);
CREATE INDEX IF NOT EXISTS idx_signals_email ON engagement_signals(email);
CREATE INDEX IF NOT EXISTS idx_signals_platform ON engagement_signals(current_platform);
CREATE INDEX IF NOT EXISTS idx_signals_level ON engagement_signals(engagement_level);
CREATE INDEX IF NOT EXISTS idx_signals_score ON engagement_signals(engagement_score DESC);

CREATE INDEX IF NOT EXISTS idx_events_lead ON engagement_events(lead_id);
CREATE INDEX IF NOT EXISTS idx_events_signal ON engagement_events(signal_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON engagement_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON engagement_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_transitions_lead ON platform_transitions(lead_id);
CREATE INDEX IF NOT EXISTS idx_transitions_created ON platform_transitions(created_at DESC);

-- ============================================================================
-- TRIGGERS
-- ============================================================================
DROP TRIGGER IF EXISTS update_signals_timestamp ON engagement_signals;
CREATE TRIGGER update_signals_timestamp
    BEFORE UPDATE ON engagement_signals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Get leads ready for transition to GHL
CREATE OR REPLACE FUNCTION get_leads_ready_for_ghl_transition()
RETURNS TABLE(
    lead_id UUID,
    email TEXT,
    engagement_score FLOAT,
    engagement_level TEXT,
    trigger_reason TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        es.lead_id,
        es.email,
        es.engagement_score,
        es.engagement_level,
        CASE
            WHEN es.emails_replied > 0 THEN 'email_reply'
            WHEN es.meetings_booked > 0 THEN 'meeting_booked'
            WHEN es.forms_submitted > 0 THEN 'form_submitted'
            WHEN es.requested_contact THEN 'requested_contact'
            WHEN es.emails_opened >= 3 AND es.last_email_open > NOW() - INTERVAL '7 days' THEN 'high_open_engagement'
            ELSE 'score_threshold'
        END as trigger_reason
    FROM engagement_signals es
    WHERE es.current_platform = 'instantly'
    AND (
        es.emails_replied > 0
        OR es.meetings_booked > 0
        OR es.forms_submitted > 0
        OR es.requested_contact = TRUE
        OR (es.emails_opened >= 3 AND es.last_email_open > NOW() - INTERVAL '7 days')
        OR es.engagement_score >= 40
    );
END;
$$ LANGUAGE plpgsql;

-- Get routing stats
CREATE OR REPLACE FUNCTION get_routing_stats()
RETURNS TABLE(
    platform TEXT,
    engagement_level TEXT,
    lead_count BIGINT,
    avg_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        es.current_platform,
        es.engagement_level,
        COUNT(*)::BIGINT,
        AVG(es.engagement_score)::FLOAT
    FROM engagement_signals es
    WHERE es.current_platform IS NOT NULL
    GROUP BY es.current_platform, es.engagement_level
    ORDER BY es.current_platform, es.engagement_level;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- DONE! Run: SELECT * FROM get_routing_stats();
-- ============================================================================
