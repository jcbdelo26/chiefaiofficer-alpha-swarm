#!/usr/bin/env python3
"""
Interactive Credential Setup Script
Guides user through configuring all required and optional API credentials.
"""

import os
import sys
from pathlib import Path

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_section(text):
    print(f"\n{Colors.CYAN}{text}{Colors.END}")
    print(f"{Colors.CYAN}{'-'*len(text)}{Colors.END}")

def get_input(prompt, current_value=None, optional=False):
    """Get user input with current value display."""
    if current_value and current_value not in ['', 'your_', 'XXX']:
        prompt_text = f"{prompt}\n  Current: {Colors.GREEN}{current_value[:20]}...{Colors.END}\n  New value (press Enter to keep): "
    else:
        if optional:
            prompt_text = f"{prompt} {Colors.YELLOW}(optional, press Enter to skip){Colors.END}: "
        else:
            prompt_text = f"{prompt}: "
    
    value = input(prompt_text).strip()
    
    if not value and current_value:
        return current_value
    return value

def setup_rb2b():
    """Configure RB2B credentials."""
    print_section("RB2B - Website Visitor Identification")
    print("1. Go to https://app.rb2b.com/")
    print("2. Navigate to Settings → API Keys")
    print("3. Generate new API key")
    print("4. Navigate to Webhooks → Create Webhook")
    print("5. Copy webhook secret\n")
    
    api_key = get_input("Enter RB2B API Key", optional=True)
    webhook_secret = get_input("Enter RB2B Webhook Secret", optional=True)
    
    return {
        'RB2B_API_KEY': api_key,
        'RB2B_WEBHOOK_SECRET': webhook_secret
    }

def setup_openai():
    """Configure OpenAI credentials."""
    print_section("OpenAI - Embeddings & Transcription")
    print("1. Go to https://platform.openai.com/")
    print("2. Click profile → View API Keys")
    print("3. Create new secret key (starts with sk-)\n")
    
    api_key = get_input("Enter OpenAI API Key", optional=True)
    
    return {'OPENAI_API_KEY': api_key}

def setup_slack():
    """Configure Slack credentials."""
    print_section("Slack - Team Notifications")
    print("1. Go to https://api.slack.com/apps")
    print("2. Create New App → From scratch")
    print("3. Name: 'Beta Swarm Monitor'")
    print("4. Navigate to Incoming Webhooks → Activate")
    print("5. Add New Webhook to Workspace")
    print("6. Copy webhook URL\n")
    
    webhook_url = get_input("Enter Slack Webhook URL", optional=True)
    bot_token = get_input("Enter Slack Bot Token (for interactive features)", optional=True)
    
    return {
        'SLACK_WEBHOOK_URL': webhook_url,
        'SLACK_BOT_TOKEN': bot_token
    }

def setup_smtp():
    """Configure SMTP credentials."""
    print_section("SMTP - Email Alerts")
    print("Choose option:")
    print("1. Gmail SMTP (free, for testing)")
    print("2. SendGrid (recommended for production)")
    print("3. Skip")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == '1':
        print("\nGmail SMTP Setup:")
        print("1. Enable 2FA on Gmail")
        print("2. Go to https://myaccount.google.com/apppasswords")
        print("3. Create app password for 'Beta Swarm'\n")
        
        return {
            'SMTP_HOST': 'smtp.gmail.com',
            'SMTP_PORT': '587',
            'SMTP_USER': get_input("Enter Gmail address"),
            'SMTP_PASSWORD': get_input("Enter 16-char app password"),
            'SMTP_FROM': get_input("Enter from email (same as Gmail)"),
            'SENDGRID_API_KEY': ''
        }
    
    elif choice == '2':
        print("\nSendGrid Setup:")
        print("1. Go to https://sendgrid.com/")
        print("2. Sign up for free tier")
        print("3. Settings → API Keys → Create API Key\n")
        
        return {
            'SMTP_HOST': '',
            'SMTP_PORT': '',
            'SMTP_USER': '',
            'SMTP_PASSWORD': '',
            'SMTP_FROM': get_input("Enter from email"),
            'SENDGRID_API_KEY': get_input("Enter SendGrid API Key")
        }
    
    return {}

def setup_twilio():
    """Configure Twilio credentials."""
    print_section("Twilio - SMS Critical Alerts (Optional)")
    print("1. Go to https://console.twilio.com/")
    print("2. Sign up for trial ($15 credit)")
    print("3. Get phone number")
    print("4. Copy Account SID and Auth Token\n")
    
    if input("Configure Twilio? (y/n): ").lower() != 'y':
        return {}
    
    return {
        'TWILIO_ACCOUNT_SID': get_input("Enter Account SID"),
        'TWILIO_AUTH_TOKEN': get_input("Enter Auth Token"),
        'TWILIO_FROM_NUMBER': get_input("Enter Twilio phone number"),
        'TWILIO_TO_NUMBER': get_input("Enter your phone for alerts")
    }

def update_env_file(credentials):
    """Update .env file with new credentials."""
    env_path = Path(__file__).parent.parent / '.env'
    
    if not env_path.exists():
        print(f"{Colors.RED}Error: .env file not found{Colors.END}")
        return False
    
    # Read current .env
    with open(env_path, 'r') as f:
        lines = f.readlines()
    
    # Update values
    updated_lines = []
    for line in lines:
        updated = False
        for key, value in credentials.items():
            if value and line.startswith(f"{key}="):
                updated_lines.append(f"{key}={value}\n")
                updated = True
                break
        
        if not updated:
            updated_lines.append(line)
    
    # Write back
    with open(env_path, 'w') as f:
        f.writelines(updated_lines)
    
    print(f"\n{Colors.GREEN}✓ .env file updated successfully{Colors.END}")
    return True

def main():
    print_header("Beta Swarm - Interactive Credential Setup")
    
    print(f"{Colors.YELLOW}This script will guide you through configuring API credentials.{Colors.END}")
    print(f"{Colors.YELLOW}You can skip optional services by pressing Enter.{Colors.END}\n")
    
    if input("Continue? (y/n): ").lower() != 'y':
        print("Setup cancelled.")
        return
    
    all_credentials = {}
    
    # Setup each service
    all_credentials.update(setup_rb2b())
    all_credentials.update(setup_openai())
    all_credentials.update(setup_slack())
    all_credentials.update(setup_smtp())
    all_credentials.update(setup_twilio())
    
    # Filter out empty values
    credentials = {k: v for k, v in all_credentials.items() if v}
    
    if not credentials:
        print(f"\n{Colors.YELLOW}No credentials entered. Exiting.{Colors.END}")
        return
    
    # Summary
    print_header("Summary")
    print(f"Credentials to update: {len(credentials)}")
    for key in credentials.keys():
        print(f"  {Colors.GREEN}✓{Colors.END} {key}")
    
    if input("\nUpdate .env file? (y/n): ").lower() == 'y':
        if update_env_file(credentials):
            print(f"\n{Colors.GREEN}Setup complete!{Colors.END}")
            print(f"\nNext steps:")
            print(f"1. Run: {Colors.BLUE}python scripts/validate_credentials.py{Colors.END}")
            print(f"2. Test integrations")
            print(f"3. Proceed to Day 21\n")
    else:
        print("\nSetup cancelled. No changes made.")

if __name__ == "__main__":
    main()
