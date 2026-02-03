#!/usr/bin/env python3
"""
Gmail Send Module
=================

Sends emails via Gmail API using OAuth 2.0 credentials.

Setup:
1. Create OAuth credentials in Google Cloud Console
2. Download credentials.json to project root
3. Run: python execution/gmail_send.py --authorize
4. Complete OAuth flow in browser
5. Token will be saved for future use

Usage:
    # Authorize (first time only)
    python execution/gmail_send.py --authorize
    
    # Send email
    python execution/gmail_send.py --to "recipient@email.com" --subject "Subject" --body "Body text"
    
    # Send from file
    python execution/gmail_send.py --to "recipient@email.com" --file message.txt
"""

import os
import sys
import json
import base64
import argparse
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional, List
import mimetypes

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    print("Google API libraries not installed. Run:")
    print("  pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")

from rich.console import Console
from rich.panel import Panel

console = Console()

# OAuth scopes - what permissions we request
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]

# File paths
PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"


class GmailClient:
    """Gmail API client for sending emails."""
    
    def __init__(self):
        self.creds = None
        self.service = None
        self.user_email = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Gmail API."""
        if not GOOGLE_AVAILABLE:
            raise RuntimeError("Google API libraries not installed")
        
        # Load existing token
        if TOKEN_FILE.exists():
            self.creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        
        # If no valid creds, get new ones
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                try:
                    self.creds.refresh(Request())
                except Exception as e:
                    console.print(f"[yellow]Token refresh failed, re-authorizing: {e}[/yellow]")
                    self.creds = None
            
            if not self.creds:
                if not CREDENTIALS_FILE.exists():
                    raise FileNotFoundError(
                        f"credentials.json not found at {CREDENTIALS_FILE}\n"
                        "Download it from Google Cloud Console → APIs → Credentials → OAuth 2.0 Client IDs"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_FILE), SCOPES
                )
                self.creds = flow.run_local_server(port=0)
            
            # Save token for future
            with open(TOKEN_FILE, 'w') as token:
                token.write(self.creds.to_json())
            console.print(f"[green]✓ Token saved to {TOKEN_FILE}[/green]")
        
        # Build Gmail service
        self.service = build('gmail', 'v1', credentials=self.creds)
        
        # Get user email
        profile = self.service.users().getProfile(userId='me').execute()
        self.user_email = profile.get('emailAddress')
        console.print(f"[green]✓ Authenticated as {self.user_email}[/green]")
    
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
        attachments: Optional[List[Path]] = None,
        cc: Optional[str] = None,
        bcc: Optional[str] = None
    ) -> dict:
        """
        Send an email.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body (plain text or HTML)
            html: If True, body is treated as HTML
            attachments: List of file paths to attach
            cc: CC recipients (comma-separated)
            bcc: BCC recipients (comma-separated)
            
        Returns:
            Sent message metadata
        """
        try:
            # Create message
            if attachments:
                message = MIMEMultipart()
                if html:
                    message.attach(MIMEText(body, 'html'))
                else:
                    message.attach(MIMEText(body, 'plain'))
                
                # Add attachments
                for file_path in attachments:
                    self._add_attachment(message, file_path)
            else:
                content_type = 'html' if html else 'plain'
                message = MIMEText(body, content_type)
            
            message['to'] = to
            message['from'] = self.user_email
            message['subject'] = subject
            
            if cc:
                message['cc'] = cc
            if bcc:
                message['bcc'] = bcc
            
            # Encode and send
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            send_message = self.service.users().messages().send(
                userId='me',
                body={'raw': encoded_message}
            ).execute()
            
            console.print(Panel.fit(
                f"[bold green]✓ Email Sent Successfully[/bold green]\n\n"
                f"From: {self.user_email}\n"
                f"To: {to}\n"
                f"Subject: {subject}\n"
                f"Message ID: {send_message['id']}",
                border_style="green"
            ))
            
            return send_message
            
        except HttpError as error:
            console.print(f"[red]Error sending email: {error}[/red]")
            raise
    
    def _add_attachment(self, message: MIMEMultipart, file_path: Path):
        """Add an attachment to the message."""
        file_path = Path(file_path)
        
        content_type, encoding = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = 'application/octet-stream'
        
        main_type, sub_type = content_type.split('/', 1)
        
        with open(file_path, 'rb') as f:
            attachment = MIMEBase(main_type, sub_type)
            attachment.set_payload(f.read())
        
        encoders.encode_base64(attachment)
        attachment.add_header(
            'Content-Disposition',
            'attachment',
            filename=file_path.name
        )
        
        message.attach(attachment)


def authorize():
    """Run OAuth authorization flow."""
    console.print("\n[bold blue]📧 Gmail OAuth Authorization[/bold blue]\n")
    
    if not CREDENTIALS_FILE.exists():
        console.print(f"[red]Error: credentials.json not found[/red]")
        console.print("\nTo create OAuth credentials:")
        console.print("1. Go to https://console.cloud.google.com/apis/credentials")
        console.print("2. Create OAuth 2.0 Client ID (Desktop app)")
        console.print("3. Download JSON and save as credentials.json")
        return False
    
    try:
        client = GmailClient()
        console.print(f"\n[green]✓ Successfully authorized as {client.user_email}[/green]")
        console.print(f"[dim]Token saved to: {TOKEN_FILE}[/dim]")
        return True
    except Exception as e:
        console.print(f"[red]Authorization failed: {e}[/red]")
        return False


def send_email_cli(args):
    """Send email from CLI arguments."""
    client = GmailClient()
    
    # Get body from file or argument
    if args.file:
        with open(args.file) as f:
            content = f.read()
        
        # Check if first line is subject
        lines = content.split('\n', 2)
        if lines[0].startswith('Subject:'):
            subject = lines[0].replace('Subject:', '').strip()
            body = '\n'.join(lines[1:]).strip()
        else:
            subject = args.subject
            body = content
    else:
        subject = args.subject
        body = args.body
    
    # Parse attachments
    attachments = None
    if args.attach:
        attachments = [Path(f) for f in args.attach]
    
    # Send
    client.send_email(
        to=args.to,
        subject=subject,
        body=body,
        html=args.html,
        attachments=attachments,
        cc=args.cc,
        bcc=args.bcc
    )


def main():
    parser = argparse.ArgumentParser(description="Send emails via Gmail API")
    
    subparsers = parser.add_subparsers(dest='command')
    
    # Authorize command
    auth_parser = subparsers.add_parser('authorize', help='Run OAuth authorization')
    
    # Send command
    send_parser = subparsers.add_parser('send', help='Send an email')
    send_parser.add_argument('--to', required=True, help='Recipient email')
    send_parser.add_argument('--subject', '-s', help='Email subject')
    send_parser.add_argument('--body', '-b', help='Email body')
    send_parser.add_argument('--file', '-f', help='Read body from file')
    send_parser.add_argument('--html', action='store_true', help='Send as HTML')
    send_parser.add_argument('--attach', nargs='+', help='Files to attach')
    send_parser.add_argument('--cc', help='CC recipients')
    send_parser.add_argument('--bcc', help='BCC recipients')
    
    args = parser.parse_args()
    
    if args.command == 'authorize' or (len(sys.argv) > 1 and sys.argv[1] == '--authorize'):
        authorize()
    elif args.command == 'send':
        send_email_cli(args)
    else:
        # Default: show help
        parser.print_help()


# Convenience function for programmatic use
def send_email(
    to: str,
    subject: str,
    body: str,
    html: bool = False,
    attachments: Optional[List[str]] = None
) -> dict:
    """
    Send an email using Gmail API.
    
    Args:
        to: Recipient email
        subject: Email subject
        body: Email body
        html: If True, body is HTML
        attachments: List of file paths to attach
        
    Returns:
        Sent message metadata
    """
    client = GmailClient()
    attach_paths = [Path(f) for f in attachments] if attachments else None
    return client.send_email(to, subject, body, html=html, attachments=attach_paths)


if __name__ == "__main__":
    main()
