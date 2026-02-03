#!/usr/bin/env python3
"""
Context MCP Server
==================
Context window management for token efficiency.

Features:
- Token estimation for various content types
- Context compaction using XML serialization
- Pre-fetch common data patterns
- Context budget tracking per agent

Tools:
- compact_context: Compress context data using XML serialization
- estimate_tokens: Estimate token count for content
- get_context_budget: Get remaining context budget for an agent
- prefetch_data: Pre-fetch and cache common data patterns
- set_context_budget: Set context budget for an agent

Usage:
    python mcp-servers/context-mcp/server.py [--dry-run]
"""

import os
import sys
import json
import re
import asyncio
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict, field
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import logging

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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("context-mcp")

DRY_RUN = False

TOKENS_PER_CHAR_ESTIMATE = 0.25
DEFAULT_CONTEXT_BUDGET = 100000

XML_COMPRESSION_RATIO = 0.6


@dataclass
class AgentContext:
    """Context tracking for an agent."""
    agent_id: str
    budget_tokens: int
    used_tokens: int
    reserved_tokens: int
    last_compaction: Optional[str]
    compactions_count: int
    efficiency_ratio: float


@dataclass
class PrefetchPattern:
    """Definition of a prefetch pattern."""
    pattern_id: str
    data_type: str
    query_template: str
    priority: int
    last_fetched: Optional[str]
    hit_count: int


class TokenEstimator:
    """Estimate token counts for various content types."""
    
    SPECIAL_TOKEN_COSTS = {
        "system_prompt": 50,
        "function_call": 20,
        "json_structure": 10
    }
    
    @staticmethod
    def estimate_text(text: str) -> int:
        """Estimate tokens for plain text (approximately 4 chars per token for English)."""
        return max(1, int(len(text) * TOKENS_PER_CHAR_ESTIMATE))
    
    @staticmethod
    def estimate_json(data: Any) -> int:
        """Estimate tokens for JSON data."""
        json_str = json.dumps(data)
        base_tokens = TokenEstimator.estimate_text(json_str)
        structure_overhead = json_str.count("{") + json_str.count("[")
        return base_tokens + structure_overhead
    
    @staticmethod
    def estimate_xml(xml_str: str) -> int:
        """Estimate tokens for XML data."""
        base_tokens = TokenEstimator.estimate_text(xml_str)
        return int(base_tokens * 0.9)
    
    @staticmethod
    def estimate_code(code: str) -> int:
        """Estimate tokens for code (higher density)."""
        return max(1, int(len(code) * 0.3))
    
    @staticmethod
    def estimate_structured(data: Dict[str, Any], content_type: str = "json") -> int:
        """Estimate tokens for structured data."""
        if content_type == "json":
            return TokenEstimator.estimate_json(data)
        elif content_type == "xml":
            xml_str = XMLSerializer.dict_to_xml(data)
            return TokenEstimator.estimate_xml(xml_str)
        else:
            return TokenEstimator.estimate_text(str(data))


class XMLSerializer:
    """Efficient XML serialization for token optimization."""
    
    @staticmethod
    def dict_to_xml(data: Dict[str, Any], root_name: str = "data") -> str:
        """Convert dictionary to compact XML."""
        root = Element(root_name)
        XMLSerializer._add_dict_elements(root, data)
        
        xml_str = tostring(root, encoding="unicode")
        return xml_str
    
    @staticmethod
    def _add_dict_elements(parent: Element, data: Dict[str, Any]):
        """Recursively add dictionary elements to XML."""
        for key, value in data.items():
            safe_key = re.sub(r'[^a-zA-Z0-9_]', '_', str(key))
            
            if value is None:
                continue
            elif isinstance(value, dict):
                child = SubElement(parent, safe_key)
                XMLSerializer._add_dict_elements(child, value)
            elif isinstance(value, list):
                child = SubElement(parent, safe_key)
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        item_elem = SubElement(child, "item")
                        XMLSerializer._add_dict_elements(item_elem, item)
                    else:
                        item_elem = SubElement(child, "item")
                        item_elem.text = str(item)
            else:
                child = SubElement(parent, safe_key)
                child.text = str(value)
    
    @staticmethod
    def pretty_xml(xml_str: str) -> str:
        """Format XML with indentation (costs more tokens but readable)."""
        try:
            parsed = minidom.parseString(xml_str)
            return parsed.toprettyxml(indent="  ")
        except Exception:
            return xml_str


class ContextCompactor:
    """Compact context data for token efficiency."""
    
    COMPACT_TEMPLATES = {
        "lead": ["email", "name", "company", "icp_tier", "intent_score"],
        "company": ["name", "domain", "industry", "size"],
        "enrichment": ["email", "verified", "title", "seniority"],
        "campaign": ["id", "subject", "status", "metrics"]
    }
    
    @staticmethod
    def compact_lead(lead: Dict[str, Any]) -> Dict[str, Any]:
        """Compact lead data to essential fields."""
        fields = ContextCompactor.COMPACT_TEMPLATES["lead"]
        return {k: lead.get(k) for k in fields if lead.get(k) is not None}
    
    @staticmethod
    def compact_list(items: List[Dict[str, Any]], data_type: str) -> str:
        """Compact a list of items into XML format."""
        template = ContextCompactor.COMPACT_TEMPLATES.get(data_type, [])
        
        compacted = []
        for item in items:
            if template:
                compacted.append({k: item.get(k) for k in template if item.get(k) is not None})
            else:
                compacted.append(item)
        
        return XMLSerializer.dict_to_xml({"items": compacted}, root_name=data_type + "s")
    
    @staticmethod
    def summarize_metrics(metrics: Dict[str, Any]) -> str:
        """Create compact summary of metrics."""
        summary_parts = []
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                summary_parts.append(f"{key}={value}")
            elif isinstance(value, dict) and "total" in value:
                summary_parts.append(f"{key}={value['total']}")
        return "|".join(summary_parts)


class ContextMCPServer:
    """
    Context window management MCP server.
    
    Features:
    - Token estimation for planning
    - Context compaction using XML
    - Budget tracking per agent
    - Pre-fetch optimization
    """
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.agent_contexts: Dict[str, AgentContext] = {}
        self.prefetch_patterns: Dict[str, PrefetchPattern] = {}
        self.storage_path = Path(__file__).parent.parent.parent / ".hive-mind" / "context"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._load_state()
    
    def _load_state(self):
        """Load persisted context state."""
        state_file = self.storage_path / "context_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                for agent_id, ctx in data.get("agents", {}).items():
                    self.agent_contexts[agent_id] = AgentContext(**ctx)
            except Exception as e:
                logger.warning(f"Failed to load context state: {e}")
    
    def _save_state(self):
        """Persist context state."""
        if self.dry_run:
            return
        
        state_file = self.storage_path / "context_state.json"
        data = {
            "agents": {k: asdict(v) for k, v in self.agent_contexts.items()},
            "saved_at": datetime.utcnow().isoformat()
        }
        with open(state_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def _get_or_create_agent(self, agent_id: str) -> AgentContext:
        """Get or create agent context."""
        if agent_id not in self.agent_contexts:
            self.agent_contexts[agent_id] = AgentContext(
                agent_id=agent_id,
                budget_tokens=DEFAULT_CONTEXT_BUDGET,
                used_tokens=0,
                reserved_tokens=0,
                last_compaction=None,
                compactions_count=0,
                efficiency_ratio=1.0
            )
        return self.agent_contexts[agent_id]
    
    async def compact_context(
        self,
        data: Any,
        data_type: str = "generic",
        format: str = "xml",
        keep_fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Compress context data for token efficiency."""
        
        original_tokens = TokenEstimator.estimate_json(data)
        
        if isinstance(data, list):
            if data_type in ContextCompactor.COMPACT_TEMPLATES:
                compacted = ContextCompactor.compact_list(data, data_type)
            else:
                compacted = XMLSerializer.dict_to_xml({"items": data}, root_name="list")
        elif isinstance(data, dict):
            if keep_fields:
                filtered = {k: data.get(k) for k in keep_fields if data.get(k) is not None}
                compacted = XMLSerializer.dict_to_xml(filtered, root_name=data_type)
            else:
                compacted = XMLSerializer.dict_to_xml(data, root_name=data_type)
        else:
            compacted = str(data)
        
        compacted_tokens = TokenEstimator.estimate_xml(compacted) if format == "xml" else TokenEstimator.estimate_text(compacted)
        
        savings = original_tokens - compacted_tokens
        compression_ratio = compacted_tokens / max(1, original_tokens)
        
        return {
            "success": True,
            "compacted": compacted,
            "format": format,
            "original_tokens": original_tokens,
            "compacted_tokens": compacted_tokens,
            "tokens_saved": savings,
            "compression_ratio": round(compression_ratio, 3)
        }
    
    async def estimate_tokens(
        self,
        content: Any,
        content_type: str = "auto"
    ) -> Dict[str, Any]:
        """Estimate token count for content."""
        
        if content_type == "auto":
            if isinstance(content, str):
                content_type = "text"
            elif isinstance(content, dict):
                content_type = "json"
            elif isinstance(content, list):
                content_type = "json"
            else:
                content_type = "text"
        
        if content_type == "text":
            tokens = TokenEstimator.estimate_text(str(content))
        elif content_type == "json":
            tokens = TokenEstimator.estimate_json(content)
        elif content_type == "xml":
            tokens = TokenEstimator.estimate_xml(str(content))
        elif content_type == "code":
            tokens = TokenEstimator.estimate_code(str(content))
        else:
            tokens = TokenEstimator.estimate_text(str(content))
        
        xml_tokens = None
        if content_type in ("json", "text") and isinstance(content, (dict, list)):
            try:
                xml_str = XMLSerializer.dict_to_xml(content if isinstance(content, dict) else {"items": content})
                xml_tokens = TokenEstimator.estimate_xml(xml_str)
            except Exception:
                pass
        
        result = {
            "success": True,
            "tokens": tokens,
            "content_type": content_type,
            "char_count": len(str(content)) if content else 0
        }
        
        if xml_tokens and xml_tokens < tokens:
            result["xml_alternative"] = {
                "tokens": xml_tokens,
                "savings": tokens - xml_tokens,
                "savings_percent": round((1 - xml_tokens / tokens) * 100, 1)
            }
        
        return result
    
    async def get_context_budget(
        self,
        agent_id: str
    ) -> Dict[str, Any]:
        """Get remaining context budget for an agent."""
        
        agent = self._get_or_create_agent(agent_id)
        
        available = agent.budget_tokens - agent.used_tokens - agent.reserved_tokens
        utilization = agent.used_tokens / max(1, agent.budget_tokens)
        
        return {
            "success": True,
            "agent_id": agent_id,
            "budget": {
                "total": agent.budget_tokens,
                "used": agent.used_tokens,
                "reserved": agent.reserved_tokens,
                "available": available
            },
            "utilization": round(utilization, 4),
            "utilization_percent": round(utilization * 100, 1),
            "efficiency_ratio": agent.efficiency_ratio,
            "compactions_count": agent.compactions_count,
            "last_compaction": agent.last_compaction,
            "recommendations": self._get_recommendations(agent, available)
        }
    
    def _get_recommendations(self, agent: AgentContext, available: int) -> List[str]:
        """Get context usage recommendations."""
        recommendations = []
        
        if available < agent.budget_tokens * 0.2:
            recommendations.append("Context budget low. Consider compacting non-essential data.")
        
        if agent.efficiency_ratio < 0.7:
            recommendations.append("Low efficiency ratio. Use XML format for structured data.")
        
        if agent.compactions_count == 0 and agent.used_tokens > agent.budget_tokens * 0.5:
            recommendations.append("Consider running context compaction to free up tokens.")
        
        return recommendations
    
    async def set_context_budget(
        self,
        agent_id: str,
        budget_tokens: Optional[int] = None,
        used_tokens: Optional[int] = None,
        reserved_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Set context budget for an agent."""
        
        if self.dry_run:
            return {"success": True, "dry_run": True, "agent_id": agent_id}
        
        agent = self._get_or_create_agent(agent_id)
        
        if budget_tokens is not None:
            agent.budget_tokens = budget_tokens
        if used_tokens is not None:
            agent.used_tokens = used_tokens
        if reserved_tokens is not None:
            agent.reserved_tokens = reserved_tokens
        
        agent.efficiency_ratio = 1 - (agent.used_tokens / max(1, agent.budget_tokens))
        
        self._save_state()
        
        return {
            "success": True,
            "agent_id": agent_id,
            "budget": asdict(agent)
        }
    
    async def prefetch_data(
        self,
        patterns: List[Dict[str, Any]],
        agent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Register and execute prefetch patterns."""
        
        if self.dry_run:
            return {"success": True, "dry_run": True, "patterns_registered": len(patterns)}
        
        registered = []
        for pattern in patterns:
            pattern_id = pattern.get("id", f"pattern_{len(self.prefetch_patterns)}")
            self.prefetch_patterns[pattern_id] = PrefetchPattern(
                pattern_id=pattern_id,
                data_type=pattern.get("data_type", "generic"),
                query_template=pattern.get("query", ""),
                priority=pattern.get("priority", 0),
                last_fetched=None,
                hit_count=0
            )
            registered.append(pattern_id)
        
        return {
            "success": True,
            "registered_patterns": registered,
            "total_patterns": len(self.prefetch_patterns)
        }
    
    async def track_context_usage(
        self,
        agent_id: str,
        tokens_used: int,
        operation: str = "unknown"
    ) -> Dict[str, Any]:
        """Track context token usage for an agent."""
        
        if self.dry_run:
            return {"success": True, "dry_run": True}
        
        agent = self._get_or_create_agent(agent_id)
        agent.used_tokens += tokens_used
        agent.efficiency_ratio = 1 - (agent.used_tokens / max(1, agent.budget_tokens))
        
        self._save_state()
        
        return {
            "success": True,
            "agent_id": agent_id,
            "tokens_added": tokens_used,
            "total_used": agent.used_tokens,
            "remaining": agent.budget_tokens - agent.used_tokens - agent.reserved_tokens
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "context-mcp",
            "timestamp": datetime.utcnow().isoformat(),
            "tracked_agents": len(self.agent_contexts),
            "prefetch_patterns": len(self.prefetch_patterns),
            "dry_run": self.dry_run
        }


TOOLS = [
    {
        "name": "compact_context",
        "description": "Compress context data using XML serialization for token efficiency.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data": {"description": "Data to compact (dict, list, or any JSON-serializable)"},
                "data_type": {
                    "type": "string",
                    "enum": ["lead", "company", "enrichment", "campaign", "generic"],
                    "default": "generic",
                    "description": "Type of data for optimized compaction"
                },
                "format": {
                    "type": "string",
                    "enum": ["xml", "minimal"],
                    "default": "xml"
                },
                "keep_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific fields to keep (for dicts)"
                }
            },
            "required": ["data"]
        }
    },
    {
        "name": "estimate_tokens",
        "description": "Estimate token count for content. Helps plan context usage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"description": "Content to estimate tokens for"},
                "content_type": {
                    "type": "string",
                    "enum": ["auto", "text", "json", "xml", "code"],
                    "default": "auto"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "get_context_budget",
        "description": "Get remaining context budget and utilization for an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent identifier"}
            },
            "required": ["agent_id"]
        }
    },
    {
        "name": "set_context_budget",
        "description": "Set context budget parameters for an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent identifier"},
                "budget_tokens": {"type": "integer", "description": "Total token budget"},
                "used_tokens": {"type": "integer", "description": "Currently used tokens"},
                "reserved_tokens": {"type": "integer", "description": "Reserved tokens for responses"}
            },
            "required": ["agent_id"]
        }
    },
    {
        "name": "prefetch_data",
        "description": "Register prefetch patterns for common data access.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patterns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "data_type": {"type": "string"},
                            "query": {"type": "string"},
                            "priority": {"type": "integer"}
                        }
                    }
                },
                "agent_id": {"type": "string"}
            },
            "required": ["patterns"]
        }
    },
    {
        "name": "track_context_usage",
        "description": "Track context token usage for an agent operation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Agent identifier"},
                "tokens_used": {"type": "integer", "description": "Tokens consumed"},
                "operation": {"type": "string", "description": "Operation name"}
            },
            "required": ["agent_id", "tokens_used"]
        }
    }
]


async def main():
    parser = argparse.ArgumentParser(description="Context MCP Server")
    parser.add_argument("--dry-run", action="store_true", help="Run without making changes")
    args = parser.parse_args()
    
    global DRY_RUN
    DRY_RUN = args.dry_run
    
    if not MCP_AVAILABLE:
        print("MCP package not available. Install with: pip install mcp")
        return
    
    server = Server("context-mcp")
    context_server = ContextMCPServer(dry_run=DRY_RUN)
    
    if DRY_RUN:
        logger.info("Running in DRY-RUN mode")
    
    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in TOOLS]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            if name == "compact_context":
                result = await context_server.compact_context(
                    arguments["data"],
                    arguments.get("data_type", "generic"),
                    arguments.get("format", "xml"),
                    arguments.get("keep_fields")
                )
            elif name == "estimate_tokens":
                result = await context_server.estimate_tokens(
                    arguments["content"],
                    arguments.get("content_type", "auto")
                )
            elif name == "get_context_budget":
                result = await context_server.get_context_budget(arguments["agent_id"])
            elif name == "set_context_budget":
                result = await context_server.set_context_budget(
                    arguments["agent_id"],
                    arguments.get("budget_tokens"),
                    arguments.get("used_tokens"),
                    arguments.get("reserved_tokens")
                )
            elif name == "prefetch_data":
                result = await context_server.prefetch_data(
                    arguments["patterns"],
                    arguments.get("agent_id")
                )
            elif name == "track_context_usage":
                result = await context_server.track_context_usage(
                    arguments["agent_id"],
                    arguments["tokens_used"],
                    arguments.get("operation", "unknown")
                )
            else:
                result = {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.exception(f"Tool error: {name}")
            result = {"error": str(e)}
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1])


if __name__ == "__main__":
    asyncio.run(main())
