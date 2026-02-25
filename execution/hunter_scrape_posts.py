#!/usr/bin/env python3
"""
Hunter Agent - LinkedIn Post Engager Scraper
=============================================
Scrapes commenters and likers from LinkedIn posts.

Usage:
    python execution/hunter_scrape_posts.py --url "https://linkedin.com/posts/..."
    python execution/hunter_scrape_posts.py --url "post_url" --include-likers --limit 100
"""

import os
import sys
import json
import uuid
import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from ratelimit import limits, sleep_and_retry
from rich.console import Console
from rich.progress import Progress

console = Console()


@dataclass
class PostEngager:
    """Normalized post engager (commenter/liker) from LinkedIn."""
    lead_id: str
    source_type: str  # post_commenter or post_liker
    source_id: str
    source_url: str
    source_name: str  # Post author name or topic
    post_topic: str
    captured_at: str
    batch_id: str
    linkedin_url: str
    linkedin_id: str
    name: str
    first_name: str
    last_name: str
    title: str
    company: str
    location: str
    engagement_action: str  # commented, liked, loved, celebrated, etc.
    engagement_content: Optional[str]  # Comment text if commenter
    engagement_timestamp: Optional[str]
    sentiment: Optional[str]  # positive, neutral, negative
    scraper_version: str = "1.0.0"


class LinkedInPostScraper:
    """Scrapes engagers from LinkedIn posts."""
    
    def __init__(self):
        self.cookie = os.getenv("LINKEDIN_COOKIE")
        self.batch_id = str(uuid.uuid4())
        
        if not self.cookie:
            raise ValueError("LINKEDIN_COOKIE not set")
    
    @sleep_and_retry
    @limits(calls=5, period=60)
    def _rate_limited_request(self, url: str, headers: dict) -> Dict[str, Any]:
        """Rate-limited HTTP request."""
        import requests
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code == 429:
            console.print("[yellow]Rate limited. Waiting 5 minutes...[/yellow]")
            time.sleep(300)
            raise Exception("Rate limited")
        
        return {
            "status": response.status_code,
            "data": response.json() if "application/json" in response.headers.get("content-type", "") else None
        }
    
    def fetch_post_engagers(self, post_url: str, include_likers: bool = True, limit: int = 100) -> List[PostEngager]:
        """
        Fetch engagers (commenters + likers) from a LinkedIn post.
        
        Commenters are prioritized as they show deeper engagement.
        
        Note: Full implementation requires browser automation.
        """
        console.print(f"\n[bold blue]🕵️ HUNTER: Scraping post engagers[/bold blue]")
        console.print(f"[dim]Post: {post_url}[/dim]")
        console.print(f"[dim]Include likers: {include_likers}[/dim]")
        
        # Extract post ID from URL
        # URLs can be like: /posts/username_activity-1234567890 or /feed/update/urn:li:activity:1234567890
        post_id = self._extract_post_id(post_url)
        
        engagers = []
        
        try:
            headers = {
                "Cookie": f"li_at={self.cookie}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            console.print(f"[yellow]Note: Full post scraping requires browser automation.[/yellow]")
            console.print(f"[dim]Would scrape up to {limit} engagers from post {post_id}[/dim]")
            
            # In production:
            # 1. Use Selenium/Playwright to navigate to post
            # 2. Click "Comments" to load comment section
            # 3. Scroll to load all comments
            # 4. Extract commenter profiles and comment text
            # 5. If include_likers, click reaction count to see likers
            # 6. Extract liker profiles
            
            return engagers
            
        except Exception as e:
            console.print(f"[red]Error scraping post: {e}[/red]")
            raise
    
    def _extract_post_id(self, post_url: str) -> str:
        """Extract post ID from various LinkedIn URL formats."""
        if "activity-" in post_url:
            # Format: /posts/username_activity-1234567890
            parts = post_url.split("activity-")
            if len(parts) > 1:
                return parts[1].split("/")[0].split("?")[0]
        elif "urn:li:activity:" in post_url:
            # Format: /feed/update/urn:li:activity:1234567890
            parts = post_url.split("urn:li:activity:")
            if len(parts) > 1:
                return parts[1].split("/")[0].split("?")[0]
        
        # Fallback: return last path segment
        return post_url.rstrip("/").split("/")[-1]
    
    def _analyze_sentiment(self, comment_text: str) -> str:
        """Simple sentiment analysis for comments."""
        if not comment_text:
            return "neutral"
        
        comment_lower = comment_text.lower()
        
        positive_signals = ["great", "love", "amazing", "excellent", "agree", "insightful", "thanks", "helpful", "brilliant"]
        negative_signals = ["disagree", "wrong", "bad", "terrible", "hate", "awful", "poor"]
        
        positive_count = sum(1 for word in positive_signals if word in comment_lower)
        negative_count = sum(1 for word in negative_signals if word in comment_lower)
        
        if positive_count > negative_count:
            return "positive"
        elif negative_count > positive_count:
            return "negative"
        else:
            return "neutral"
    
    def _normalize_engager(self, raw: Dict[str, Any], post_url: str, post_topic: str, is_commenter: bool) -> PostEngager:
        """Normalize raw engager data to our schema."""
        
        full_name = raw.get("name", "")
        name_parts = full_name.split(" ", 1)
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        
        headline = raw.get("headline", "")
        title = ""
        company = ""
        if " at " in headline:
            parts = headline.split(" at ", 1)
            title = parts[0].strip()
            company = parts[1].strip()
        else:
            title = headline
        
        comment_text = raw.get("comment", "") if is_commenter else None
        sentiment = self._analyze_sentiment(comment_text) if comment_text else None
        
        return PostEngager(
            lead_id=str(uuid.uuid4()),
            source_type="post_commenter" if is_commenter else "post_liker",
            source_id=self._extract_post_id(post_url),
            source_url=post_url,
            source_name=raw.get("post_author", "LinkedIn Post"),
            post_topic=post_topic,
            captured_at=datetime.utcnow().isoformat(),
            batch_id=self.batch_id,
            linkedin_url=raw.get("publicIdentifier", ""),
            linkedin_id=raw.get("entityUrn", "").split(":")[-1],
            name=full_name,
            first_name=first_name,
            last_name=last_name,
            title=title,
            company=company,
            location=raw.get("location", ""),
            engagement_action="commented" if is_commenter else raw.get("reaction_type", "liked"),
            engagement_content=comment_text,
            engagement_timestamp=raw.get("timestamp"),
            sentiment=sentiment
        )
    
    def save_engagers(self, engagers: List[PostEngager], output_dir: Optional[Path] = None) -> Path:
        """Save scraped engagers to JSON file."""
        
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / ".hive-mind" / "scraped"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"post_engagers_{self.batch_id[:8]}_{timestamp}.json"
        output_path = output_dir / filename
        
        # Separate commenters and likers for stats
        commenters = [e for e in engagers if e.source_type == "post_commenter"]
        likers = [e for e in engagers if e.source_type == "post_liker"]
        
        engagers_data = [asdict(e) for e in engagers]
        
        with open(output_path, "w") as f:
            json.dump({
                "batch_id": self.batch_id,
                "scraped_at": datetime.utcnow().isoformat(),
                "source_type": "post_engager",
                "lead_count": len(engagers),
                "commenter_count": len(commenters),
                "liker_count": len(likers),
                "leads": engagers_data
            }, f, indent=2)
        
        console.print(f"[green]✅ Saved {len(engagers)} engagers to {output_path}[/green]")
        console.print(f"[dim]   Commenters: {len(commenters)}, Likers: {len(likers)}[/dim]")
        
        return output_path


def main():
    parser = argparse.ArgumentParser(description="Scrape LinkedIn post engagers")
    parser.add_argument("--url", required=True, help="LinkedIn post URL")
    parser.add_argument("--topic", default="", help="Post topic for context")
    parser.add_argument("--include-likers", action="store_true", default=True, help="Include likers (not just commenters)")
    parser.add_argument("--commenters-only", action="store_true", help="Only scrape commenters")
    parser.add_argument("--limit", type=int, default=100, help="Max engagers to scrape")
    
    args = parser.parse_args()
    
    include_likers = not args.commenters_only
    
    try:
        scraper = LinkedInPostScraper()
        engagers = scraper.fetch_post_engagers(args.url, include_likers, args.limit)
        
        if engagers:
            output_path = scraper.save_engagers(engagers)
            console.print(f"\n[bold green]✅ Post scraping complete![/bold green]")
            console.print(f"Next step: python execution/enricher_waterfall.py --input {output_path}")
        else:
            console.print("\n[yellow]No engagers scraped. Full implementation requires browser automation.[/yellow]")
            
    except Exception as e:
        console.print(f"[red]❌ Post scraping failed: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
