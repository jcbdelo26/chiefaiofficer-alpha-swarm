#!/usr/bin/env python3
"""
YouTube Video Insight Ingestor
==============================
Extracts transcripts from YouTube videos and generates actionable
improvement plans for the CAIO Alpha Swarm.

Usage:
    python scripts/ingest_video_insight.py --url "https://youtube.com/watch?v=..." --focus "agent_handoffs"

Dependencies:
    pip install youtube-transcript-api rich
"""

import argparse
import sys
import re
from pathlib import Path
from typing import Optional, List

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.markdown import Markdown
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.formatters import TextFormatter
except ImportError:
    print("Dependencies missing. Run: pip install youtube-transcript-api rich")
    sys.exit(1)

# Add project root to path to import core modules if needed
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

console = Console()

def extract_video_id(url: str) -> Optional[str]:
    """Extract video ID from various YouTube URL formats."""
    patterns = [
        r"(?:v=|\/)([0-9A-Za-z_-]{11})",
        r"(?:youtu\.be\/)([0-9A-Za-z_-]{11})",
        r"(?:embed\/)([0-9A-Za-z_-]{11})"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def get_transcript(video_id: str) -> str:
    """Fetch transcript using youtube_transcript_api."""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        formatter = TextFormatter()
        text = formatter.format_transcript(transcript_list)
        return text
    except Exception as e:
        console.print(f"[red]Error fetching transcript: {e}[/red]")
        sys.exit(1)

def generate_prompt(video_id: str, transcript: str, focus: str) -> str:
    """Generate a prompt for the swarm to analyze the transcript."""
    return f"""# YouTube Insight Analysis: {focus}

**Source Video ID**: `{video_id}`
**Request**: Identify improvements for CAIO Alpha Swarm based on this transcript.

## Focus Area
{focus}

## Transcript Content
(First 15k chars for prompt context)

{transcript[:15000]}... [truncated for context limits]

## Required Output
1. **Core Insight**: What specific pattern/technique should we steal?
2. **Code Adaptation**: Which file(s) in `d:/Agent Swarm Orchestration/chiefaiofficer-alpha-swarm` should change?
3. **Implementation Plan**: 3-step plan to code this now.
"""

def main():
    parser = argparse.ArgumentParser(description="Ingest YouTube insights for Swarm improvement")
    parser.add_argument("--url", required=True, help="YouTube Video URL")
    parser.add_argument("--focus", default="general_improvement", help="Focus area (e.g., 'routing', 'memory', 'testing')")
    parser.add_argument("--output", "-o", help="Output markdown file for the analysis request")
    
    args = parser.parse_args()
    
    video_id = extract_video_id(args.url)
    if not video_id:
        console.print("[red]Invalid YouTube URL[/red] (Expected format: youtube.com/watch?v=...)")
        return
        
    console.print(f"[cyan]Fetching transcript for video ID: {video_id}...[/cyan]")
    transcript = get_transcript(video_id)
    
    console.print(f"[green]Transcript fetched ({len(transcript)} chars).[/green]")
    
    analysis_content = generate_prompt(video_id, transcript, args.focus)
    
    filename = args.output or f"docs/video_insights/insight_{video_id}_{args.focus}.md"
    output_file = PROJECT_ROOT / filename
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(analysis_content)
        
    console.print(Panel(
        f"[bold]Insight Ready![/bold]\n\n"
        f"Transcript saved and Prompt generated at:\n"
        f"[yellow]{output_file}[/yellow]\n\n"
        f"To verify/implement, simply copy the content of this file into your AI assistant chat.",
        title="Success"
    ))

if __name__ == "__main__":
    main()
