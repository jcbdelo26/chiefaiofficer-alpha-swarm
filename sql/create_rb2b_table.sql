-- RB2B Visitors Table
-- Run this in Supabase SQL Editor

CREATE TABLE IF NOT EXISTS rb2b_visitors (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    rb2b_visitor_id TEXT UNIQUE,
    company_name TEXT,
    company_domain TEXT,
    company_industry TEXT,
    company_size TEXT,
    company_revenue TEXT,
    company_location TEXT,
    visitor_ip TEXT,
    visitor_country TEXT,
    visitor_city TEXT,
    page_url TEXT,
    referrer TEXT,
    user_agent TEXT,
    session_id TEXT,
    identified_at TIMESTAMPTZ,
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast lookups
CREATE INDEX IF NOT EXISTS idx_rb2b_company_domain 
ON rb2b_visitors(company_domain);

CREATE INDEX IF NOT EXISTS idx_rb2b_identified_at 
ON rb2b_visitors(identified_at DESC);

-- Success message
SELECT 'RB2B visitors table created successfully!' as message;
