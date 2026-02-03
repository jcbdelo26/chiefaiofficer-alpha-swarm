#!/usr/bin/env python3
"""Generate sample emails for Phase 2 quality review."""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

async def generate_samples():
    from core.website_intent_monitor import get_website_monitor
    
    monitor = get_website_monitor()
    
    test_visitors = [
        {
            'visitor_id': 'sample_vp_sales_001',
            'email': 'mike.johnson@acmesaas.com',
            'first_name': 'Mike',
            'last_name': 'Johnson',
            'company_name': 'Acme SaaS',
            'company_domain': 'gong.io',
            'job_title': 'VP of Sales',
            'pages_viewed': ['/blog/how-pg-cut-product-development-time-22-percent'],
            'work_history': [{'company_name': 'Outreach', 'company_domain': 'outreach.io'}]
        },
        {
            'visitor_id': 'sample_cro_002',
            'email': 'sarah.chen@techcorp.io',
            'first_name': 'Sarah',
            'last_name': 'Chen',
            'company_name': 'TechCorp',
            'company_domain': 'techcorp.io',
            'job_title': 'Chief Revenue Officer',
            'pages_viewed': ['/blog/sales-ai-frameworks-2026'],
            'work_history': [{'company_name': 'Salesforce', 'company_domain': 'salesforce.com'}]
        },
        {
            'visitor_id': 'sample_revops_003',
            'email': 'alex.smith@growthco.com',
            'first_name': 'Alex',
            'last_name': 'Smith',
            'company_name': 'GrowthCo',
            'company_domain': 'gong.io',
            'job_title': 'RevOps Director',
            'pages_viewed': ['/blog/ai-efficiency-roi-metrics'],
            'work_history': [{'company_name': 'Gong', 'company_domain': 'gong.io'}]
        },
        {
            'visitor_id': 'sample_head_sales_004',
            'email': 'jennifer.lee@cloudops.io',
            'first_name': 'Jennifer',
            'last_name': 'Lee',
            'company_name': 'CloudOps',
            'company_domain': 'cloudops.io',
            'job_title': 'Head of Sales',
            'pages_viewed': ['/blog/implementation-guide-ai-sales'],
            'work_history': []
        }
    ]
    
    generated = 0
    for v in test_visitors:
        print(f"Processing {v['email']}...")
        result = await monitor.process_visitor(v)
        if result:
            print(f"  Score: {result.intent_score}, Queued: {result.queued_for_approval}")
            if result.queued_for_approval:
                generated += 1
        else:
            print(f"  No result (filtered)")
    
    print(f"\nGenerated {generated} sample emails for quality review")

if __name__ == "__main__":
    asyncio.run(generate_samples())
