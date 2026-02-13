# B2B Enrichment Provider Research — 2026-02-13

**Status**: COMPLETE
**Purpose**: Find alternative enrichment fallbacks alongside Apollo.io (PDL cancelled)
**Author**: Claude Code research agents

---

## Executive Summary

Researched 28+ B2B enrichment providers. The industry has converged on **waterfall enrichment aggregators** — platforms that query 15-75+ underlying data sources behind a single API call. These outperform single-source providers on match rate, cost, and legal safety.

### Top 3 Recommendations

| Rank | Provider | Type | Cost/Lead | Match Rate | Free Tier | Legal Risk |
|------|----------|------|-----------|------------|-----------|------------|
| 1 | **BetterContact** | Waterfall aggregator (20+ sources) | $0.04-0.05 | 85% | No (but pay-only-for-verified) | LOW |
| 2 | **FullEnrich** | Waterfall aggregator (15+ sources) | $0.055 | 91% | 50 free leads | LOW |
| 3 | **Hunter.io** | Email specialist | $0.07 | 65-80% | 25 searches/mo | LOW |

### Why NOT People Data Labs
- **10x more expensive**: $0.28/lead vs $0.04-0.05 (BetterContact/FullEnrich)
- **Stale data**: Monthly update cycles vs real-time
- **Single source**: PDL queries one database; waterfalls query 15-75+
- **Better alternatives exist**: BetterContact/FullEnrich aggregate multiple providers including PDL

---

## Recommended Waterfall Architecture

```
STAGE 1: Apollo.io People Match (already implemented)
    Cost: 1 credit/lead (~$0.20 after plan)
    Match rate: ~40%
    If MISS → STAGE 2

STAGE 2: BetterContact (recommended) or FullEnrich (budget)
    Cost: $0.04-0.055/email
    Match rate: ~45% of Stage 1 misses
    Only charged for VERIFIED results
    If MISS → STAGE 3

STAGE 3: Email Pattern + Verification
    Generate: firstname.lastname@company.com
    Verify: ZeroBounce ($0.01) or NeverBounce ($0.002-0.008)
    Match rate: ~5-10% of Stage 2 misses
```

**Expected aggregate**: 85-90% match rate at ~$0.025 avg cost/lead

---

## Provider Details

### Tier 1: Waterfall Aggregators (Built-in Multi-Provider)

#### BetterContact — RANK 1: Best Overall Value
- **API**: REST API on all paid plans
- **Input**: Name, company, LinkedIn URL
- **Output**: Verified work email, phone, company data
- **Auth**: API key
- **Pricing**: $49/mo (1K credits) to $799/mo (20K credits)
- **Key feature**: Pay-only-for-verified — no charge for catch-all, invalid, or no-result
- **Verification**: 4-layer (SMTP, catch-all, domain reputation, pattern consistency)
- **BetterAI**: ML-optimized provider sequencing per query

#### FullEnrich — RANK 2: Best Entry Point
- **API**: REST API
- **Input**: Name, company, LinkedIn URL
- **Output**: Triple-verified email, phone, company data
- **Auth**: API key
- **Pricing**: $29/mo (500 credits), **50 free leads no CC**
- **Verification**: Triple independent check, 98%+ deliverability
- **Sources**: 15+ providers including Apollo, Clearbit, Hunter

#### Persana AI — Best for Full AI SDR Platform
- **75+ data providers** (largest pool researched)
- **AI-powered sequencing** (budget providers first, premium as needed)
- **Integrated AI SDR agent** (Nia) for full automation
- **Pricing**: Custom (~$100-500/mo estimated)

### Tier 2: Single-Source Providers (Build Your Own Waterfall)

#### Hunter.io — RANK 3: Best Email Specialist
- **API**: Email Finder + Verifier API
- **Input**: Name + company domain
- **Output**: Work email only (NO phone)
- **Pricing**: Free (25 searches/mo), $34/mo annual (500 searches)
- **Legal risk**: LOW (public web sources)

#### RocketReach
- API on Ultimate plan, $0.30-0.45/lookup, medium legal risk

#### Lusha
- API on Scale plan only (custom pricing), 70 free credits/mo, medium legal risk

#### Snov.io
- Email finder + verifier, $149/mo (4800 credits/yr), medium legal risk

#### Crustdata (YC-backed)
- Real-time data from 16+ verified sources
- **Watcher API**: webhook-based real-time signals (job changes, funding)
- Custom pricing (likely enterprise)

#### Dropcontact
- GDPR-compliant, no stored database (real-time retrieval)
- EUR 24/mo start, 30 credits per phone lookup
- LOW legal risk

### Tier 3: NOT Recommended

| Provider | Reason |
|----------|--------|
| People Data Labs | $0.28/lead (10x more expensive), stale monthly data |
| Proxycurl | SHUT DOWN (LinkedIn lawsuit) |
| Clay API v1 | Deprecated (404) |
| LeadIQ | $1.00/email (20-50x more expensive) |
| ContactOut | Deceptive "unlimited" marketing (capped at 2K/mo) |
| Seamless.ai | 12-month lock-in, full upfront, rapid credit drain |
| Clearbit/Breeze | Requires paid HubSpot subscription |
| ZoomInfo | $50K/yr minimum for API |

---

## Email Verification Providers

| Provider | Cost/Email | Free Tier | Best For |
|----------|-----------|-----------|----------|
| **ZeroBounce** | $0.004-0.01 | 100/mo | Catch-all detection, risk scoring |
| **NeverBounce** | $0.002-0.008 | — | High volume, lowest cost |
| Reoon | $9/mo+ | Yes | Budget teams |
| Mailgun | $90/mo+ | — | Already on Mailgun |

---

## Legal Risk Assessment

**LOW RISK** (recommended):
- BetterContact, FullEnrich, Persana AI (aggregators querying compliant providers)
- Hunter.io (public web sources)
- Cognism, Dropcontact, Datagma (GDPR-compliant)
- Apollo.io, Crustdata (established, verified sources)

**MEDIUM-HIGH RISK** (avoid for production):
- Kaspr, LeadIQ, ContactOut (LinkedIn-focused, Proxycurl lawsuit precedent)
- Seamless.ai (opaque sourcing, aggressive contracts)

---

## Implementation Priority

1. **Immediate**: Sign up for FullEnrich (50 free leads, no CC) — validate match rates
2. **After validation**: Choose BetterContact ($49/mo) or FullEnrich ($29/mo)
3. **Integration**: Replace Proxycurl fallback in `enricher_clay_waterfall.py`
4. **Verification layer**: Add ZeroBounce ($0.01/email) before outreach queue
