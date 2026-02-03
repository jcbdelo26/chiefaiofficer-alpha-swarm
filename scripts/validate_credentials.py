#!/usr/bin/env python3
"""
Credential Validation Script
Validates all API credentials and webhooks are properly configured.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'

def check_env_var(var_name, required=True):
    """Check if environment variable is set and not placeholder."""
    value = os.getenv(var_name)
    
    if not value or value in ['', 'your_', 'XXX', 'YYY', 'ZZZ']:
        if required:
            print(f"{Colors.RED}✗{Colors.END} {var_name}: MISSING (required)")
            return False
        else:
            print(f"{Colors.YELLOW}○{Colors.END} {var_name}: Not configured (optional)")
            return None
    else:
        print(f"{Colors.GREEN}✓{Colors.END} {var_name}: Configured")
        return True

def test_openai():
    """Test OpenAI API connection."""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return False
    
    try:
        import openai
        openai.api_key = api_key
        # Simple test - list models
        models = openai.Model.list()
        print(f"{Colors.GREEN}✓{Colors.END} OpenAI API: Connected")
        return True
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.END} OpenAI API: Failed - {str(e)}")
        return False

def test_slack_webhook():
    """Test Slack webhook."""
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    if not webhook_url or 'XXX' in webhook_url:
        return False
    
    try:
        response = requests.post(
            webhook_url,
            json={'text': '🧪 Beta Swarm credential validation test'},
            timeout=5
        )
        if response.status_code == 200:
            print(f"{Colors.GREEN}✓{Colors.END} Slack Webhook: Connected")
            return True
        else:
            print(f"{Colors.RED}✗{Colors.END} Slack Webhook: Failed (status {response.status_code})")
            return False
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.END} Slack Webhook: Failed - {str(e)}")
        return False

def test_smtp():
    """Test SMTP connection."""
    smtp_host = os.getenv('SMTP_HOST')
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')
    
    if not all([smtp_host, smtp_user, smtp_password]):
        return None
    
    try:
        import smtplib
        server = smtplib.SMTP(smtp_host, int(os.getenv('SMTP_PORT', 587)))
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.quit()
        print(f"{Colors.GREEN}✓{Colors.END} SMTP: Connected")
        return True
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.END} SMTP: Failed - {str(e)}")
        return False

def main():
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}Beta Swarm - Credential Validation{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    results = {
        'required': [],
        'optional': [],
        'failed': []
    }
    
    # Required APIs
    print(f"{Colors.BLUE}Required APIs:{Colors.END}")
    required_vars = [
        'GHL_API_KEY',
        'GHL_LOCATION_ID',
        'LINKEDIN_EMAIL',
        'LINKEDIN_COOKIE',
        'CLAY_API_KEY',
        'SUPABASE_URL',
        'SUPABASE_KEY',
        'INSTANTLY_API_KEY',
        'ANTHROPIC_API_KEY',
    ]
    
    for var in required_vars:
        result = check_env_var(var, required=True)
        if result:
            results['required'].append(var)
        else:
            results['failed'].append(var)
    
    print(f"\n{Colors.BLUE}Optional APIs:{Colors.END}")
    optional_vars = [
        ('RB2B_API_KEY', 'Visitor identification'),
        ('RB2B_WEBHOOK_SECRET', 'Visitor webhooks'),
        ('OPENAI_API_KEY', 'Embeddings & transcription'),
        ('EXA_API_KEY', 'Web research'),
        ('SLACK_WEBHOOK_URL', 'Team notifications'),
        ('SMTP_USER', 'Email alerts'),
        ('SENDGRID_API_KEY', 'Email alerts (alternative)'),
        ('TWILIO_ACCOUNT_SID', 'SMS alerts'),
    ]
    
    for var, purpose in optional_vars:
        result = check_env_var(var, required=False)
        if result:
            results['optional'].append(var)
        elif result is None:
            pass  # Not configured
        else:
            results['failed'].append(var)
    
    # Connection tests
    print(f"\n{Colors.BLUE}Connection Tests:{Colors.END}")
    
    if os.getenv('OPENAI_API_KEY'):
        test_openai()
    
    if os.getenv('SLACK_WEBHOOK_URL') and 'XXX' not in os.getenv('SLACK_WEBHOOK_URL'):
        test_slack_webhook()
    
    if os.getenv('SMTP_USER'):
        test_smtp()
    
    # Summary
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}Summary:{Colors.END}")
    print(f"{Colors.GREEN}✓{Colors.END} Required APIs configured: {len(results['required'])}/{len(required_vars)}")
    print(f"{Colors.GREEN}✓{Colors.END} Optional APIs configured: {len(results['optional'])}")
    
    if results['failed']:
        print(f"{Colors.RED}✗{Colors.END} Failed/Missing: {len(results['failed'])}")
        print(f"  Missing: {', '.join(results['failed'])}")
    
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")
    
    # Exit code
    if len(results['required']) < len(required_vars):
        print(f"{Colors.YELLOW}⚠ Some required APIs are not configured{Colors.END}")
        print(f"Run: {Colors.BLUE}python scripts/setup_credentials.py{Colors.END} for guided setup\n")
        sys.exit(1)
    else:
        print(f"{Colors.GREEN}✓ All required APIs configured!{Colors.END}\n")
        sys.exit(0)

if __name__ == "__main__":
    main()
