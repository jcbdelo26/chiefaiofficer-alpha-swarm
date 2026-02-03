#!/usr/bin/env python3
"""
Hunter MCP Server
=================
MCP server providing LinkedIn scraping tools for the Alpha Swarm.

Tools:
- scrape_followers: Scrape company page followers
- scrape_events: Scrape event attendees
- scrape_groups: Scrape group members
- scrape_posts: Scrape post engagers

Usage:
    python mcp-servers/hunter-mcp/server.py
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("Warning: MCP package not installed. Run 'pip install mcp'")


# Tool definitions
TOOLS = [
    {
        "name": "hunter_scrape_followers",
        "description": "Scrape followers from a LinkedIn company page. Returns normalized lead data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_url": {
                    "type": "string",
                    "description": "LinkedIn company URL (e.g., https://linkedin.com/company/gong)"
                },
                "company_name": {
                    "type": "string",
                    "description": "Human-readable company name"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum followers to scrape",
                    "default": 100
                }
            },
            "required": ["company_url"]
        }
    },
    {
        "name": "hunter_scrape_event",
        "description": "Scrape attendees from a LinkedIn event.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_url": {
                    "type": "string",
                    "description": "LinkedIn event URL"
                },
                "event_name": {
                    "type": "string",
                    "description": "Event name for context"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum attendees to scrape",
                    "default": 100
                }
            },
            "required": ["event_url"]
        }
    },
    {
        "name": "hunter_scrape_group",
        "description": "Scrape members from a LinkedIn group.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "group_url": {
                    "type": "string",
                    "description": "LinkedIn group URL"
                },
                "group_name": {
                    "type": "string",
                    "description": "Group name for context"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum members to scrape",
                    "default": 100
                }
            },
            "required": ["group_url"]
        }
    },
    {
        "name": "hunter_scrape_post",
        "description": "Scrape engagers (commenters and likers) from a LinkedIn post.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "post_url": {
                    "type": "string",
                    "description": "LinkedIn post URL"
                },
                "include_likers": {
                    "type": "boolean",
                    "description": "Whether to include likers (not just commenters)",
                    "default": True
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum engagers to scrape",
                    "default": 100
                }
            },
            "required": ["post_url"]
        }
    },
    {
        "name": "hunter_status",
        "description": "Get current Hunter agent status including rate limit state and session health.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]


class HunterMCPServer:
    """MCP server for LinkedIn scraping operations."""
    
    def __init__(self):
        self.linkedin_cookie = os.getenv("LINKEDIN_COOKIE")
        self.daily_count = 0
        self.hourly_count = 0
        self.last_request = None
        
    def get_status(self) -> dict:
        """Get current scraper status."""
        return {
            "session_valid": bool(self.linkedin_cookie),
            "daily_count": self.daily_count,
            "hourly_count": self.hourly_count,
            "daily_limit": 500,
            "hourly_limit": 100,
            "last_request": self.last_request,
            "status": "ready" if self.linkedin_cookie else "no_session"
        }
    
    async def handle_scrape_followers(self, company_url: str, company_name: str = "", limit: int = 100) -> dict:
        """Handle follower scraping request."""
        # Import the actual scraper
        from execution.hunter_scrape_followers import LinkedInFollowerScraper
        
        try:
            scraper = LinkedInFollowerScraper()
            leads = scraper.fetch_followers(company_url, company_name or company_url.split("/")[-1], limit)
            
            if leads:
                output_path = scraper.save_leads(leads)
                return {
                    "success": True,
                    "leads_count": len(leads),
                    "output_file": str(output_path),
                    "batch_id": scraper.batch_id
                }
            else:
                return {
                    "success": True,
                    "leads_count": 0,
                    "message": "No leads scraped (scaffold mode)"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def handle_scrape_event(self, event_url: str, event_name: str = "", limit: int = 100) -> dict:
        """Handle event attendee scraping request."""
        # Placeholder - implement in execution/hunter_scrape_events.py
        return {
            "success": True,
            "message": "Event scraping not yet implemented",
            "event_url": event_url
        }
    
    async def handle_scrape_group(self, group_url: str, group_name: str = "", limit: int = 100) -> dict:
        """Handle group member scraping request."""
        # Placeholder - implement in execution/hunter_scrape_groups.py
        return {
            "success": True,
            "message": "Group scraping not yet implemented",
            "group_url": group_url
        }
    
    async def handle_scrape_post(self, post_url: str, include_likers: bool = True, limit: int = 100) -> dict:
        """Handle post engager scraping request."""
        # Placeholder - implement in execution/hunter_scrape_posts.py
        return {
            "success": True,
            "message": "Post scraping not yet implemented",
            "post_url": post_url
        }


async def main():
    """Run the MCP server."""
    
    if not MCP_AVAILABLE:
        print("MCP package not available. Install with: pip install mcp")
        return
    
    server = Server("hunter-mcp")
    hunter = HunterMCPServer()
    
    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in TOOLS]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        if name == "hunter_scrape_followers":
            result = await hunter.handle_scrape_followers(
                arguments["company_url"],
                arguments.get("company_name", ""),
                arguments.get("limit", 100)
            )
        elif name == "hunter_scrape_event":
            result = await hunter.handle_scrape_event(
                arguments["event_url"],
                arguments.get("event_name", ""),
                arguments.get("limit", 100)
            )
        elif name == "hunter_scrape_group":
            result = await hunter.handle_scrape_group(
                arguments["group_url"],
                arguments.get("group_name", ""),
                arguments.get("limit", 100)
            )
        elif name == "hunter_scrape_post":
            result = await hunter.handle_scrape_post(
                arguments["post_url"],
                arguments.get("include_likers", True),
                arguments.get("limit", 100)
            )
        elif name == "hunter_status":
            result = hunter.get_status()
        else:
            result = {"error": f"Unknown tool: {name}"}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1])


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
