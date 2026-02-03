# 🕵️ LinkedIn Scraping SOP
# Standard Operating Procedure for HUNTER Agent

---

## Overview

This directive governs all LinkedIn data extraction activities performed by the HUNTER agent. Compliance with these rules is **MANDATORY** to maintain account safety and data quality.

---

## Authorized Data Sources

### 1. Competitor Followers
**URL Pattern**: `https://linkedin.com/company/{company}/followers/`
**Script**: `execution/hunter_scrape_followers.py`

**Target Competitors**:
| Competitor | LinkedIn URL | Priority |
|------------|--------------|----------|
| Gong | linkedin.com/company/gabordi | P0 |
| Clari | linkedin.com/company/clari | P0 |
| Chorus | linkedin.com/company/chorus-ai | P1 |
| People.ai | linkedin.com/company/people-ai | P1 |
| Outreach | linkedin.com/company/outabordi | P2 |

**Data Captured**:
- Profile URL
- Name
- Headline (Title @ Company)
- Location
- Connection degree
- Follow date (if available)

### 2. Event Attendees
**URL Pattern**: `https://linkedin.com/events/{event_id}/`
**Script**: `execution/hunter_scrape_events.py`

**Target Event Types**:
- AI/ML in Sales conferences
- RevOps summits
- Sales enablement webinars
- Pipeline management workshops
- Forecasting roundtables

**Data Captured**:
- Profile URL
- Name
- Title
- Company
- Registration status
- Attendance date

### 3. Group Members
**URL Pattern**: `https://linkedin.com/groups/{group_id}/`
**Script**: `execution/hunter_scrape_groups.py`

**Target Groups**:
| Group | Members | Priority |
|-------|---------|----------|
| Revenue Collective | 15K+ | P0 |
| RevOps Co-op | 8K+ | P0 |
| Sales Operations Professionals | 45K+ | P1 |
| Modern Sales Pros | 25K+ | P1 |
| SaaS Sales Leaders | 12K+ | P2 |

**Data Captured**:
- Profile URL
- Name
- Title
- Company
- Member since
- Recent activity (posts/comments)

### 4. Post Engagers
**URL Pattern**: `https://linkedin.com/feed/update/{post_id}/`
**Script**: `execution/hunter_scrape_posts.py`

**Target Post Types**:
- Competitor thought leadership posts
- Industry influencer posts
- Trending RevOps content
- Our own viral posts (engagement mining)

**Data Captured (Commenters)**:
- Profile URL
- Name
- Title
- Company
- Comment text verbatim
- Comment timestamp
- Reaction to other comments

**Data Captured (Likers)**:
- Profile URL
- Name
- Title
- Company
- Reaction type (Like, Celebrate, etc.)

---

## Rate Limiting Rules

### CRITICAL: These limits are NON-NEGOTIABLE

| Activity | Limit | Window | Cooldown |
|----------|-------|--------|----------|
| Profile views | 100 | Hour | 5 min between bursts |
| Search queries | 20 | Hour | 30 sec between |
| Page scrolls | 50 | Session | 2 sec between |
| Daily total | 500 | 24 hours | Reset at midnight UTC |

### Implementation

```python
from ratelimit import limits, sleep_and_retry

ONE_MINUTE = 60
ONE_HOUR = 3600

@sleep_and_retry
@limits(calls=5, period=ONE_MINUTE)
def scrape_profile(profile_url: str):
    """Rate-limited profile scraping"""
    pass

@sleep_and_retry  
@limits(calls=100, period=ONE_HOUR)
def scrape_with_hourly_limit():
    """Hourly limit enforcement"""
    pass
```

### Backoff Protocol

When encountering rate limit signals:
1. **Warning**: 429 response → Wait 5 minutes
2. **Soft Block**: CAPTCHA → Wait 1 hour, rotate session
3. **Hard Block**: Account notice → STOP immediately, alert team

---

## Session Management

### Cookie Rotation

```python
# Session pool configuration
SESSIONS = [
    {"name": "primary", "cookie": os.getenv("LINKEDIN_COOKIE_1")},
    {"name": "secondary", "cookie": os.getenv("LINKEDIN_COOKIE_2")},
    {"name": "tertiary", "cookie": os.getenv("LINKEDIN_COOKIE_3")},
]

# Rotate every 100 requests
SESSION_ROTATION_THRESHOLD = 100
```

### Session Health Checks

Run before each scraping batch:
```python
def check_session_health(session_cookie: str) -> bool:
    """
    Returns True if session is valid
    Checks:
    - Cookie not expired
    - No pending security challenges
    - Profile accessible
    """
    pass
```

---

## Data Normalization

### Output Schema

All scraped data MUST conform to this schema:

```json
{
  "lead_id": "uuid-v4",
  "source": {
    "type": "competitor_follower|event_attendee|group_member|post_commenter|post_liker",
    "source_id": "linkedin_entity_id",
    "source_url": "https://linkedin.com/...",
    "source_name": "Gong",
    "captured_at": "2026-01-12T16:00:00Z",
    "batch_id": "uuid-v4"
  },
  "profile": {
    "linkedin_url": "https://linkedin.com/in/username",
    "linkedin_id": "username",
    "name": "Full Name",
    "first_name": "First",
    "last_name": "Last",
    "title": "VP of Revenue",
    "company": "Acme Inc",
    "company_linkedin_url": "https://linkedin.com/company/acme",
    "location": "San Francisco, CA",
    "connection_degree": 2,
    "profile_image_url": "https://..."
  },
  "engagement_context": {
    "action": "commented|liked|registered|joined|followed",
    "content": "Their actual comment text if applicable",
    "content_hash": "md5 of content",
    "timestamp": "2026-01-10T14:30:00Z",
    "sentiment": "positive|neutral|negative"
  },
  "raw_data": {
    "html_excerpt": "...",
    "scrape_method": "selenium|api|hybrid"
  },
  "meta": {
    "scraped_at": "2026-01-12T16:00:00Z",
    "scraper_version": "1.0.0",
    "session_id": "primary"
  }
}
```

---

## Deduplication Rules

### Dedup Key
`linkedin_url` is the primary dedup key.

### Dedup Logic
```python
def should_create_lead(linkedin_url: str, source_type: str) -> bool:
    """
    Returns True if we should create a new lead record
    
    Rules:
    - New profile: Always create
    - Existing profile, same source: Skip
    - Existing profile, new source: Add source to profile
    """
    existing = get_lead_by_linkedin_url(linkedin_url)
    
    if not existing:
        return True
    
    # Add new source to existing lead
    if source_type not in existing.sources:
        add_source_to_lead(existing, source_type)
        return False
    
    return False
```

---

## Error Handling

### Common Errors

| Error | Detection | Response |
|-------|-----------|----------|
| Rate Limited | HTTP 429 | Wait + retry with backoff |
| CAPTCHA | DOM element | Pause + rotate session |
| Profile Not Found | HTTP 404 | Log + skip |
| Private Profile | DOM indicator | Log + skip |
| Session Expired | HTTP 401 | Refresh cookie |
| Network Error | Timeout | Retry 3x |

### Error Logging

All errors logged to `.hive-mind/errors/hunter_{date}.json`:
```json
{
  "timestamp": "2026-01-12T16:00:00Z",
  "error_type": "rate_limit",
  "url": "https://...",
  "response_code": 429,
  "session_id": "primary",
  "retry_attempt": 2,
  "resolved": true
}
```

---

## Compliance Reminders

1. **Terms of Service**: We operate in gray area - minimize footprint
2. **GDPR/CCPA**: Store only necessary data, honor deletion requests
3. **Robots.txt**: Not all routes blocked, but be respectful
4. **Ethical Scraping**: Don't overwhelm servers, space out requests

---

## Daily Operations

### Morning Routine (9 AM)
1. Check session health
2. Review yesterday's scrape volumes
3. Clear any blocked sessions
4. Queue today's sources

### Scraping Windows
- **Primary**: 10 AM - 12 PM (when users active)
- **Secondary**: 2 PM - 4 PM
- **Avoid**: Before 8 AM, after 8 PM (suspicious)

### End of Day
1. Generate scrape report
2. Push leads to enrichment queue
3. Rotate sessions if needed
4. Archive raw data

---

## Metrics & Monitoring

### Daily KPIs
| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Leads scraped | 200+ | < 100 |
| Success rate | > 95% | < 90% |
| Error rate | < 5% | > 10% |
| Rate limit hits | < 3 | > 10 |
| Sessions active | 3 | < 2 |

---

*Directive Version: 1.0*
*Last Updated: 2026-01-12*
*Owner: HUNTER Agent*
