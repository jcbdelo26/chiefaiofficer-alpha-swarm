#!/usr/bin/env python3
"""
Enricher MCP Server
===================
MCP server providing lead enrichment tools via Clay, RB2B, and Exa.

Tools:
- enrich_lead: Full lead enrichment via Clay waterfall
- rb2b_match: Match lead to website visitors
- company_intel: Deep company research
- detect_intent: Intent signal detection

Usage:
    python mcp-servers/enricher-mcp/server.py
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

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


TOOLS = [
    {
        "name": "enricher_enrich_lead",
        "description": "Enrich a lead with contact data, company intel, and intent signals via Clay waterfall.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "linkedin_url": {"type": "string", "description": "LinkedIn profile URL"},
                "name": {"type": "string", "description": "Full name"},
                "company": {"type": "string", "description": "Company name"},
                "email": {"type": "string", "description": "Known email (optional)"}
            },
            "required": ["linkedin_url"]
        }
    },
    {
        "name": "enricher_rb2b_match",
        "description": "Match a lead against RB2B website visitor data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "linkedin_url": {"type": "string"},
                "email": {"type": "string"},
                "company": {"type": "string"}
            }
        }
    },
    {
        "name": "enricher_company_intel",
        "description": "Get deep company intelligence including tech stack, funding, and news.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string", "description": "Company name"},
                "domain": {"type": "string", "description": "Company domain"}
            },
            "required": ["company_name"]
        }
    },
    {
        "name": "enricher_detect_intent",
        "description": "Detect intent signals for a lead/company.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_name": {"type": "string"},
                "domain": {"type": "string"},
                "linkedin_url": {"type": "string"}
            },
            "required": ["company_name"]
        }
    },
    {
        "name": "enricher_batch_enrich",
        "description": "Enrich a batch of leads from a JSON file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_file": {"type": "string", "description": "Path to JSON file with leads"},
                "limit": {"type": "integer", "default": 50}
            },
            "required": ["input_file"]
        }
    }
]


class EnricherMCPServer:
    """MCP server for lead enrichment operations."""
    
    def __init__(self):
        self.clay_api_key = os.getenv("CLAY_API_KEY")
        self.rb2b_api_key = os.getenv("RB2B_API_KEY")
        self.exa_api_key = os.getenv("EXA_API_KEY")
        
    async def enrich_lead(self, linkedin_url: str, name: str = "", company: str = "", email: str = "") -> Dict[str, Any]:
        """Enrich a single lead via Clay waterfall."""
        try:
            from execution.enricher_clay_waterfall import ClayEnricher
            
            enricher = ClayEnricher()
            result = enricher.enrich_lead(
                lead_id="mcp_request",
                linkedin_url=linkedin_url,
                name=name,
                company=company
            )
            
            if result:
                from dataclasses import asdict
                return {"success": True, "enrichment": asdict(result)}
            else:
                return {"success": False, "error": "No enrichment data found"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def rb2b_match(self, linkedin_url: str = "", email: str = "", company: str = "") -> Dict[str, Any]:
        """Match lead against RB2B visitor data."""
        if not self.rb2b_api_key:
            return {"success": False, "error": "RB2B_API_KEY not configured"}
        
        try:
            import requests
            
            headers = {
                "Authorization": f"Bearer {self.rb2b_api_key}",
                "Content-Type": "application/json"
            }
            
            # Search RB2B for matching visitors
            params = {}
            if email:
                params["email"] = email
            if linkedin_url:
                params["linkedin_url"] = linkedin_url
            if company:
                params["company"] = company
            
            response = requests.get(
                "https://api.rb2b.com/v1/visitors/search",
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "matches": data.get("visitors", []),
                    "match_count": len(data.get("visitors", []))
                }
            else:
                return {"success": True, "matches": [], "match_count": 0}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def company_intel(self, company_name: str, domain: str = "") -> Dict[str, Any]:
        """Get deep company intelligence."""
        intel = {
            "company_name": company_name,
            "domain": domain,
            "researched_at": datetime.utcnow().isoformat()
        }
        
        # Try Exa Search for company research
        if self.exa_api_key:
            try:
                from exa_py import Exa
                
                client = Exa(api_key=self.exa_api_key)
                
                # Search for company news and info
                results = client.search(
                    f"{company_name} company news funding",
                    num_results=5,
                    type="neural"
                )
                
                intel["news"] = [
                    {"title": r.title, "url": r.url, "snippet": r.text[:200] if r.text else ""}
                    for r in results.results
                ]
                intel["success"] = True
                
            except Exception as e:
                intel["exa_error"] = str(e)
        
        return intel
    
    async def detect_intent(self, company_name: str, domain: str = "", linkedin_url: str = "") -> Dict[str, Any]:
        """Detect intent signals for a company/lead."""
        signals = []
        score = 0
        
        # Check for hiring signals via Exa
        if self.exa_api_key:
            try:
                from exa_py import Exa
                
                client = Exa(api_key=self.exa_api_key)
                
                # Search for hiring signals
                hiring_results = client.search(
                    f"{company_name} hiring sales revenue operations",
                    num_results=3,
                    type="neural"
                )
                
                if hiring_results.results:
                    signals.append("hiring_signal")
                    score += 30
                
                # Search for funding signals
                funding_results = client.search(
                    f"{company_name} funding raised series",
                    num_results=3,
                    type="neural"
                )
                
                if funding_results.results:
                    # Check if recent (simple heuristic)
                    signals.append("funding_signal")
                    score += 25
                    
            except Exception:
                pass
        
        return {
            "success": True,
            "company": company_name,
            "signals": signals,
            "intent_score": min(score, 100),
            "detected_at": datetime.utcnow().isoformat()
        }
    
    async def batch_enrich(self, input_file: str, limit: int = 50) -> Dict[str, Any]:
        """Batch enrich leads from a JSON file."""
        try:
            from execution.enricher_clay_waterfall import ClayEnricher
            
            enricher = ClayEnricher()
            enriched = enricher.enrich_batch(Path(input_file))
            
            if enriched:
                output_path = enricher.save_enriched(enriched)
                return {
                    "success": True,
                    "enriched_count": len(enriched),
                    "output_file": str(output_path)
                }
            else:
                return {"success": True, "enriched_count": 0}
                
        except Exception as e:
            return {"success": False, "error": str(e)}


async def main():
    if not MCP_AVAILABLE:
        print("MCP package not available. Install with: pip install mcp")
        return
    
    server = Server("enricher-mcp")
    enricher = EnricherMCPServer()
    
    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in TOOLS]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            if name == "enricher_enrich_lead":
                result = await enricher.enrich_lead(
                    arguments["linkedin_url"],
                    arguments.get("name", ""),
                    arguments.get("company", ""),
                    arguments.get("email", "")
                )
            elif name == "enricher_rb2b_match":
                result = await enricher.rb2b_match(
                    arguments.get("linkedin_url", ""),
                    arguments.get("email", ""),
                    arguments.get("company", "")
                )
            elif name == "enricher_company_intel":
                result = await enricher.company_intel(
                    arguments["company_name"],
                    arguments.get("domain", "")
                )
            elif name == "enricher_detect_intent":
                result = await enricher.detect_intent(
                    arguments["company_name"],
                    arguments.get("domain", ""),
                    arguments.get("linkedin_url", "")
                )
            elif name == "enricher_batch_enrich":
                result = await enricher.batch_enrich(
                    arguments["input_file"],
                    arguments.get("limit", 50)
                )
            else:
                result = {"error": f"Unknown tool: {name}"}
                
        except Exception as e:
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1])


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
