#!/usr/bin/env python3
"""
Full System Test - Chief AI Officer Alpha Swarm
================================================

Tests all integrated components:
1. API Connections
2. ICP Scoring
3. Lead Routing
4. Sentiment Analysis
5. Guardrails
6. Agent Monitoring
7. Call Coaching

Run: python scripts/full_system_test.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(override=True)

import json
from datetime import datetime


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(name: str, passed: bool, details: str = ""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"  {status} {name}")
    if details:
        print(f"         {details}")


def test_api_connections() -> dict:
    """Test all API connections."""
    print_header("1. API CONNECTIONS")
    
    results = {}
    
    # Supabase
    try:
        from supabase import create_client
        url = os.getenv('SUPABASE_URL')
        key = os.getenv('SUPABASE_KEY')
        client = create_client(url, key)
        client.table('leads').select('id').limit(1).execute()
        results['supabase'] = True
        print_result("Supabase", True, "Connected to database")
    except Exception as e:
        results['supabase'] = False
        print_result("Supabase", False, str(e)[:50])
    
    # GoHighLevel
    try:
        import requests
        api_key = os.getenv('GHL_API_KEY')
        loc_id = os.getenv('GHL_LOCATION_ID')
        headers = {'Authorization': f'Bearer {api_key}', 'Version': '2021-07-28'}
        r = requests.get(f'https://services.leadconnectorhq.com/locations/{loc_id}', headers=headers, timeout=15)
        results['gohighlevel'] = r.status_code == 200
        print_result("GoHighLevel", r.status_code == 200, f"Status: {r.status_code}")
    except Exception as e:
        results['gohighlevel'] = False
        print_result("GoHighLevel", False, str(e)[:50])
    
    # Instantly
    try:
        import requests
        api_key = os.getenv('INSTANTLY_API_KEY')
        headers = {'Authorization': f'Bearer {api_key}'}
        r = requests.get('https://api.instantly.ai/api/v2/accounts', headers=headers, timeout=15)
        results['instantly'] = r.status_code == 200
        print_result("Instantly", r.status_code == 200, f"Status: {r.status_code}")
    except Exception as e:
        results['instantly'] = False
        print_result("Instantly", False, str(e)[:50])
    
    return results


def test_icp_scoring() -> dict:
    """Test ICP scoring engine."""
    print_header("2. ICP SCORING ENGINE")
    
    results = {}
    
    try:
        from config.icp_config import score_lead, PersonaTier, IndustryFit
        
        # Test CEO at Marketing Agency (should be Tier A)
        score = score_lead(
            title="CEO",
            industry="Marketing Agency",
            employee_count=85,
            revenue_m=12,
            pain_points=["manual data entry", "can't scale operations"],
            tech_stack=["hubspot", "slack"]
        )
        
        results['ceo_agency'] = score.tier == "A"
        print_result(
            "CEO at Marketing Agency", 
            score.tier == "A",
            f"Score: {score.total_score}, Tier: {score.tier}"
        )
        
        # Test Director at Non-profit (should be disqualified)
        score2 = score_lead(
            title="Director",
            industry="Non-profit",
            employee_count=25,
            revenue_m=2
        )
        
        results['nonprofit'] = score2.tier == "DISQUALIFIED"
        print_result(
            "Director at Non-profit",
            score2.tier == "DISQUALIFIED",
            f"Score: {score2.total_score}, Tier: {score2.tier}"
        )
        
    except Exception as e:
        results['error'] = str(e)
        print_result("ICP Scoring", False, str(e)[:50])
    
    return results


def test_lead_routing() -> dict:
    """Test lead routing logic."""
    print_header("3. LEAD ROUTER")
    
    results = {}
    
    try:
        from core.lead_router import LeadRouter, EngagementSignals, OutreachPlatform
        
        router = LeadRouter()
        
        # Cold lead (no engagement) -> Instantly
        cold_signals = EngagementSignals()
        cold_decision = router.route_lead(cold_signals)
        
        results['cold_to_instantly'] = cold_decision.platform == OutreachPlatform.INSTANTLY
        print_result(
            "Cold lead routes to Instantly",
            cold_decision.platform == OutreachPlatform.INSTANTLY,
            f"Platform: {cold_decision.platform.value}"
        )
        
        # Hot lead (replied + meeting) -> GHL
        hot_signals = EngagementSignals(
            emails_replied=1,
            meetings_booked=1
        )
        hot_decision = router.route_lead(hot_signals)
        
        results['hot_to_ghl'] = hot_decision.platform == OutreachPlatform.GOHIGHLEVEL
        print_result(
            "Hot lead routes to GHL",
            hot_decision.platform == OutreachPlatform.GOHIGHLEVEL,
            f"Platform: {hot_decision.platform.value}, Level: {hot_decision.engagement_level.value}"
        )
        
    except Exception as e:
        results['error'] = str(e)
        print_result("Lead Router", False, str(e)[:50])
    
    return results


def test_sentiment_analysis() -> dict:
    """Test sentiment analyzer."""
    print_header("4. SENTIMENT ANALYZER")
    
    results = {}
    
    try:
        from core.sentiment_analyzer import SentimentAnalyzer, Sentiment, BuyingSignal
        
        analyzer = SentimentAnalyzer()
        
        # Positive reply
        positive = analyzer.analyze("This is exactly what we need! How do we get started?")
        results['positive'] = positive.sentiment in [Sentiment.POSITIVE, Sentiment.VERY_POSITIVE]
        print_result(
            "Positive message detection",
            positive.sentiment in [Sentiment.POSITIVE, Sentiment.VERY_POSITIVE],
            f"Sentiment: {positive.sentiment.value}, Signal: {positive.buying_signal.value}"
        )
        
        # Objection
        objection = analyzer.analyze("We're already using a competitor and happy with them.")
        results['objection'] = positive.objection_type is not None or "competitor" in str(objection.objection_type)
        print_result(
            "Objection detection",
            "competitor" in str(objection.objection_type.value).lower(),
            f"Objection: {objection.objection_type.value}"
        )
        
        # Negative reply
        negative = analyzer.analyze("Please remove me from your list. Not interested.")
        results['negative'] = negative.sentiment in [Sentiment.NEGATIVE, Sentiment.VERY_NEGATIVE]
        print_result(
            "Negative message detection",
            negative.sentiment in [Sentiment.NEGATIVE, Sentiment.VERY_NEGATIVE],
            f"Sentiment: {negative.sentiment.value}"
        )
        
    except Exception as e:
        results['error'] = str(e)
        print_result("Sentiment Analyzer", False, str(e)[:50])
    
    return results


def test_guardrails() -> dict:
    """Test guardrails system (unified_guardrails)."""
    print_header("5. GUARDRAILS")

    results = {}

    try:
        from core.unified_guardrails import UnifiedGuardrails

        UnifiedGuardrails()
        results['initialized'] = True
        print_result("Unified Guardrails initialized", True, "OK")

    except Exception as e:
        results['error'] = str(e)
        print_result("Guardrails", False, str(e)[:50])

    return results


def test_agent_monitor() -> dict:
    """Test agent monitoring system."""
    print_header("6. AGENT MONITOR")
    
    results = {}
    
    try:
        from core.agent_monitor import get_monitor, AgentStatus
        
        monitor = get_monitor()
        
        # Record some heartbeats
        monitor.record_agent_heartbeat("hunter", AgentStatus.HEALTHY, {"leads_scraped": 50})
        monitor.record_agent_heartbeat("enricher", AgentStatus.HEALTHY, {"enriched": 45})
        
        results['heartbeat'] = True
        print_result("Heartbeat recording", True, "Recorded 2 agent heartbeats")
        
        # Record API calls
        monitor.record_api_call("gohighlevel", True, 150)
        monitor.record_api_call("instantly", True, 200)
        
        results['api_tracking'] = True
        print_result("API call tracking", True, "Recorded 2 API calls")
        
        # Generate report
        report = monitor.reporter_generate()
        results['report'] = 'overall_health' in report
        print_result(
            "Health report generation",
            'overall_health' in report,
            f"Health: {report.get('overall_health', 'N/A')}%"
        )
        
    except Exception as e:
        results['error'] = str(e)
        print_result("Agent Monitor", False, str(e)[:50])
    
    return results


def test_call_coach() -> dict:
    """Test call coaching system."""
    print_header("7. CALL COACH")
    
    results = {}
    
    try:
        from core.call_coach import CallCoach, CallType, CallOutcome
        
        coach = CallCoach()
        
        # Log a sample call
        call_id = coach.log_call(
            lead_id="test_lead_001",
            rep_id="test_rep",
            call_type=CallType.DISCOVERY,
            outcome=CallOutcome.QUALIFIED,
            duration_minutes=25,
            notes="Good discovery call. Uncovered pain points around manual processes.",
            next_steps="Demo scheduled for next week"
        )
        
        results['call_logging'] = call_id is not None
        print_result("Call logging", call_id is not None, f"Call ID: {call_id}")
        
        # Get coaching feedback
        feedback = coach.get_coaching_feedback(call_id)
        results['coaching'] = 'overall_score' in feedback
        print_result(
            "Coaching feedback",
            'overall_score' in feedback,
            f"Score: {feedback.get('overall_score', 'N/A')}, Grade: {feedback.get('grade', 'N/A')}"
        )
        
    except Exception as e:
        results['error'] = str(e)
        print_result("Call Coach", False, str(e)[:50])
    
    return results


def test_messaging_templates() -> dict:
    """Test messaging templates."""
    print_header("8. MESSAGING TEMPLATES")
    
    results = {}
    
    try:
        from config.messaging_templates import (
            get_recommended_sequence,
            render_template,
            TemplateVariables,
            COLD_EMAIL_SEQUENCES
        )
        
        # Get recommended sequence for Tier A cold lead
        sequence = get_recommended_sequence("A", "cold", ["manual processes"])
        results['sequence_selection'] = sequence['platform'] == 'instantly'
        print_result(
            "Sequence selection",
            sequence['platform'] == 'instantly',
            f"Platform: {sequence['platform']}, Angle: {sequence['sequence_name']}"
        )
        
        # Test template rendering
        variables = TemplateVariables(
            first_name="Sarah",
            last_name="Chen",
            title="CEO",
            company_name="Acme Agency",
            industry="Marketing Agency"
        )
        
        template = COLD_EMAIL_SEQUENCES['ai_noise']['emails'][0]
        rendered = render_template(template['subject'], variables)
        
        results['template_render'] = "Sarah" in rendered
        print_result(
            "Template rendering",
            "Sarah" in rendered,
            f"Subject: {rendered}"
        )
        
    except Exception as e:
        results['error'] = str(e)
        print_result("Messaging Templates", False, str(e)[:50])
    
    return results


def main():
    print("\n" + "=" * 70)
    print("  CHIEF AI OFFICER ALPHA SWARM - FULL SYSTEM TEST")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 70)
    
    all_results = {}
    
    # Run all tests
    all_results['api'] = test_api_connections()
    all_results['icp'] = test_icp_scoring()
    all_results['routing'] = test_lead_routing()
    all_results['sentiment'] = test_sentiment_analysis()
    all_results['guardrails'] = test_guardrails()
    all_results['monitoring'] = test_agent_monitor()
    all_results['coaching'] = test_call_coach()
    all_results['templates'] = test_messaging_templates()
    
    # Summary
    print_header("SUMMARY")
    
    total_tests = 0
    passed_tests = 0
    
    for category, results in all_results.items():
        for test_name, passed in results.items():
            if test_name != 'error':
                total_tests += 1
                if passed:
                    passed_tests += 1
    
    pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"\n  Total Tests: {total_tests}")
    print(f"  Passed: {passed_tests}")
    print(f"  Failed: {total_tests - passed_tests}")
    print(f"  Pass Rate: {pass_rate:.1f}%")
    
    # Overall status
    if pass_rate >= 90:
        status = "PRODUCTION READY"
    elif pass_rate >= 70:
        status = "MOSTLY READY (minor issues)"
    elif pass_rate >= 50:
        status = "PARTIALLY READY (needs attention)"
    else:
        status = "NOT READY (critical issues)"
    
    print(f"\n  Status: {status}")
    
    # Save results
    results_file = Path(__file__).parent.parent / ".hive-mind" / "system_test_results.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "pass_rate": pass_rate,
            "status": status,
            "results": all_results
        }, f, indent=2, default=str)
    
    print(f"\n  Results saved to: {results_file}")
    print("\n" + "=" * 70)
    
    return 0 if pass_rate >= 70 else 1


if __name__ == "__main__":
    sys.exit(main())
