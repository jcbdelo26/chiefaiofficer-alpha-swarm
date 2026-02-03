#!/usr/bin/env python3
"""
Cache MCP Server
================
Intelligent caching layer for all API calls with multi-tier storage.

Cache Types:
- memory (hot): Fast in-memory cache for frequently accessed data
- disk (warm): Persistent disk cache for less frequent access
- skip (real-time): Bypass cache for real-time requirements

TTL Configuration:
- intent: 24h (intent signals change frequently)
- enrichment: 7d (company data fairly stable)
- company: 30d (firmographic data rarely changes)

Tools:
- cache_get: Retrieve cached value
- cache_set: Store value in cache
- cache_invalidate: Invalidate cache entries
- cache_stats: Get cache statistics
- cache_warm: Pre-warm cache with common patterns

Usage:
    python mcp-servers/cache-mcp/server.py [--dry-run]
"""

import os
import sys
import json
import gzip
import hashlib
import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Literal
from dataclasses import dataclass, asdict, field
from collections import OrderedDict
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
logger = logging.getLogger("cache-mcp")

DRY_RUN = False

TTL_CONFIG = {
    "intent": timedelta(hours=24),
    "enrichment": timedelta(days=7),
    "company": timedelta(days=30),
    "contact": timedelta(days=14),
    "api_response": timedelta(hours=1),
    "template": timedelta(days=1),
    "default": timedelta(hours=6)
}

COMPRESSION_THRESHOLD = 1024


@dataclass
class CacheEntry:
    """Represents a cached value."""
    key: str
    value: Any
    data_type: str
    tier: str  # memory, disk
    created_at: str
    expires_at: str
    size_bytes: int
    compressed: bool
    access_count: int = 0
    last_accessed: str = ""


@dataclass
class CacheStats:
    """Cache statistics."""
    memory_entries: int = 0
    disk_entries: int = 0
    memory_size_bytes: int = 0
    disk_size_bytes: int = 0
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    compressions: int = 0
    cost_saved_estimate: float = 0.0


class MemoryCache:
    """LRU memory cache with size limits."""
    
    def __init__(self, max_entries: int = 1000, max_size_mb: float = 100):
        self.max_entries = max_entries
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.current_size = 0
    
    def get(self, key: str) -> Optional[CacheEntry]:
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        if datetime.fromisoformat(entry.expires_at) < datetime.utcnow():
            del self.cache[key]
            self.current_size -= entry.size_bytes
            return None
        
        self.cache.move_to_end(key)
        entry.access_count += 1
        entry.last_accessed = datetime.utcnow().isoformat()
        return entry
    
    def set(self, entry: CacheEntry) -> bool:
        while (len(self.cache) >= self.max_entries or 
               self.current_size + entry.size_bytes > self.max_size_bytes):
            if not self.cache:
                return False
            oldest_key, oldest_entry = self.cache.popitem(last=False)
            self.current_size -= oldest_entry.size_bytes
        
        if entry.key in self.cache:
            self.current_size -= self.cache[entry.key].size_bytes
        
        self.cache[entry.key] = entry
        self.current_size += entry.size_bytes
        return True
    
    def delete(self, key: str) -> bool:
        if key in self.cache:
            self.current_size -= self.cache[key].size_bytes
            del self.cache[key]
            return True
        return False
    
    def clear(self):
        self.cache.clear()
        self.current_size = 0
    
    def stats(self) -> Dict[str, Any]:
        return {
            "entries": len(self.cache),
            "size_bytes": self.current_size,
            "max_entries": self.max_entries,
            "max_size_bytes": self.max_size_bytes
        }


class DiskCache:
    """Persistent disk cache with compression."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(__file__).parent.parent.parent / ".hive-mind" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / "index.json"
        self.index: Dict[str, Dict] = self._load_index()
    
    def _load_index(self) -> Dict[str, Dict]:
        if self.index_path.exists():
            try:
                with open(self.index_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_index(self):
        with open(self.index_path, "w") as f:
            json.dump(self.index, f)
    
    def _key_to_path(self, key: str) -> Path:
        hash_key = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{hash_key}.cache"
    
    def get(self, key: str) -> Optional[CacheEntry]:
        if key not in self.index:
            return None
        
        meta = self.index[key]
        if datetime.fromisoformat(meta["expires_at"]) < datetime.utcnow():
            self.delete(key)
            return None
        
        file_path = self._key_to_path(key)
        if not file_path.exists():
            del self.index[key]
            self._save_index()
            return None
        
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            
            if meta.get("compressed"):
                data = gzip.decompress(data)
            
            value = json.loads(data.decode("utf-8"))
            
            meta["access_count"] = meta.get("access_count", 0) + 1
            meta["last_accessed"] = datetime.utcnow().isoformat()
            self._save_index()
            
            return CacheEntry(
                key=key,
                value=value,
                data_type=meta["data_type"],
                tier="disk",
                created_at=meta["created_at"],
                expires_at=meta["expires_at"],
                size_bytes=meta["size_bytes"],
                compressed=meta.get("compressed", False),
                access_count=meta.get("access_count", 1),
                last_accessed=meta.get("last_accessed", "")
            )
        except Exception as e:
            logger.error(f"Failed to read cache: {e}")
            return None
    
    def set(self, entry: CacheEntry) -> bool:
        try:
            file_path = self._key_to_path(entry.key)
            data = json.dumps(entry.value).encode("utf-8")
            compressed = False
            
            if len(data) > COMPRESSION_THRESHOLD:
                data = gzip.compress(data)
                compressed = True
            
            with open(file_path, "wb") as f:
                f.write(data)
            
            self.index[entry.key] = {
                "data_type": entry.data_type,
                "created_at": entry.created_at,
                "expires_at": entry.expires_at,
                "size_bytes": len(data),
                "compressed": compressed,
                "access_count": 0,
                "last_accessed": ""
            }
            self._save_index()
            return True
        except Exception as e:
            logger.error(f"Failed to write cache: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        if key not in self.index:
            return False
        
        file_path = self._key_to_path(key)
        if file_path.exists():
            file_path.unlink()
        
        del self.index[key]
        self._save_index()
        return True
    
    def clear(self):
        for file in self.cache_dir.glob("*.cache"):
            file.unlink()
        self.index.clear()
        self._save_index()
    
    def stats(self) -> Dict[str, Any]:
        total_size = sum(m.get("size_bytes", 0) for m in self.index.values())
        return {
            "entries": len(self.index),
            "size_bytes": total_size,
            "compressed_count": sum(1 for m in self.index.values() if m.get("compressed"))
        }


class CacheMCPServer:
    """
    Multi-tier caching MCP server.
    
    Provides intelligent caching with:
    - Memory (hot) tier for fast access
    - Disk (warm) tier for persistence
    - TTL configuration per data type
    - Compression for large responses
    - Hit/miss tracking for cost analysis
    """
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.memory = MemoryCache()
        self.disk = DiskCache()
        self.stats = CacheStats()
        
        self.api_costs = {
            "enrichment": 0.05,
            "intent": 0.02,
            "company": 0.03,
            "contact": 0.01,
            "default": 0.01
        }
    
    def _get_ttl(self, data_type: str) -> timedelta:
        return TTL_CONFIG.get(data_type, TTL_CONFIG["default"])
    
    async def cache_get(
        self,
        key: str,
        tier: Literal["memory", "disk", "both"] = "both"
    ) -> Dict[str, Any]:
        """Get value from cache."""
        
        entry = None
        
        if tier in ("memory", "both"):
            entry = self.memory.get(key)
            if entry:
                self.stats.hits += 1
                return {
                    "success": True,
                    "hit": True,
                    "tier": "memory",
                    "value": entry.value,
                    "data_type": entry.data_type,
                    "age_seconds": (datetime.utcnow() - datetime.fromisoformat(entry.created_at)).total_seconds()
                }
        
        if tier in ("disk", "both") and not entry:
            entry = self.disk.get(key)
            if entry:
                self.stats.hits += 1
                if tier == "both":
                    self.memory.set(entry)
                return {
                    "success": True,
                    "hit": True,
                    "tier": "disk",
                    "value": entry.value,
                    "data_type": entry.data_type,
                    "age_seconds": (datetime.utcnow() - datetime.fromisoformat(entry.created_at)).total_seconds()
                }
        
        self.stats.misses += 1
        return {"success": True, "hit": False, "value": None}
    
    async def cache_set(
        self,
        key: str,
        value: Any,
        data_type: str = "default",
        tier: Literal["memory", "disk", "both"] = "both",
        ttl_seconds: Optional[int] = None
    ) -> Dict[str, Any]:
        """Store value in cache."""
        
        if self.dry_run:
            return {"success": True, "dry_run": True, "would_cache": key}
        
        now = datetime.utcnow()
        ttl = timedelta(seconds=ttl_seconds) if ttl_seconds else self._get_ttl(data_type)
        
        value_json = json.dumps(value)
        size_bytes = len(value_json.encode("utf-8"))
        compressed = size_bytes > COMPRESSION_THRESHOLD
        
        if compressed:
            self.stats.compressions += 1
        
        entry = CacheEntry(
            key=key,
            value=value,
            data_type=data_type,
            tier=tier,
            created_at=now.isoformat(),
            expires_at=(now + ttl).isoformat(),
            size_bytes=size_bytes,
            compressed=compressed
        )
        
        results = {"success": True, "key": key, "data_type": data_type, "tiers": []}
        
        if tier in ("memory", "both"):
            if self.memory.set(entry):
                results["tiers"].append("memory")
        
        if tier in ("disk", "both"):
            if self.disk.set(entry):
                results["tiers"].append("disk")
        
        results["size_bytes"] = size_bytes
        results["compressed"] = compressed
        results["expires_at"] = entry.expires_at
        
        return results
    
    async def cache_invalidate(
        self,
        key: Optional[str] = None,
        pattern: Optional[str] = None,
        data_type: Optional[str] = None,
        tier: Literal["memory", "disk", "both"] = "both"
    ) -> Dict[str, Any]:
        """Invalidate cache entries."""
        
        if self.dry_run:
            return {"success": True, "dry_run": True, "would_invalidate": key or pattern or data_type}
        
        invalidated = {"memory": 0, "disk": 0}
        
        if key:
            if tier in ("memory", "both") and self.memory.delete(key):
                invalidated["memory"] += 1
                self.stats.evictions += 1
            if tier in ("disk", "both") and self.disk.delete(key):
                invalidated["disk"] += 1
                self.stats.evictions += 1
        
        elif data_type:
            if tier in ("memory", "both"):
                keys_to_delete = [k for k, v in self.memory.cache.items() if v.data_type == data_type]
                for k in keys_to_delete:
                    self.memory.delete(k)
                    invalidated["memory"] += 1
                    self.stats.evictions += 1
            
            if tier in ("disk", "both"):
                keys_to_delete = [k for k, m in self.disk.index.items() if m.get("data_type") == data_type]
                for k in keys_to_delete:
                    self.disk.delete(k)
                    invalidated["disk"] += 1
                    self.stats.evictions += 1
        
        elif pattern:
            if tier in ("memory", "both"):
                keys_to_delete = [k for k in self.memory.cache.keys() if pattern in k]
                for k in keys_to_delete:
                    self.memory.delete(k)
                    invalidated["memory"] += 1
                    self.stats.evictions += 1
            
            if tier in ("disk", "both"):
                keys_to_delete = [k for k in self.disk.index.keys() if pattern in k]
                for k in keys_to_delete:
                    self.disk.delete(k)
                    invalidated["disk"] += 1
                    self.stats.evictions += 1
        
        return {"success": True, "invalidated": invalidated}
    
    async def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        
        memory_stats = self.memory.stats()
        disk_stats = self.disk.stats()
        
        hit_rate = self.stats.hits / max(1, self.stats.hits + self.stats.misses)
        
        self.stats.cost_saved_estimate = self.stats.hits * self.api_costs["default"]
        
        return {
            "success": True,
            "memory": memory_stats,
            "disk": disk_stats,
            "performance": {
                "hits": self.stats.hits,
                "misses": self.stats.misses,
                "hit_rate": round(hit_rate, 4),
                "evictions": self.stats.evictions,
                "compressions": self.stats.compressions
            },
            "cost_analysis": {
                "estimated_api_cost_saved": round(self.stats.cost_saved_estimate, 2),
                "cache_efficiency": round(hit_rate * 100, 1)
            },
            "ttl_config": {k: str(v) for k, v in TTL_CONFIG.items()}
        }
    
    async def cache_warm(
        self,
        patterns: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Pre-warm cache with common data patterns."""
        
        if self.dry_run:
            return {"success": True, "dry_run": True, "patterns": len(patterns)}
        
        warmed = 0
        for pattern in patterns:
            key = pattern.get("key")
            value = pattern.get("value")
            data_type = pattern.get("data_type", "default")
            
            if key and value:
                await self.cache_set(key, value, data_type)
                warmed += 1
        
        return {"success": True, "warmed_entries": warmed}
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "cache-mcp",
            "timestamp": datetime.utcnow().isoformat(),
            "memory_entries": len(self.memory.cache),
            "disk_entries": len(self.disk.index),
            "dry_run": self.dry_run
        }


TOOLS = [
    {
        "name": "cache_get",
        "description": "Retrieve a cached value. Returns hit/miss status and the value if found.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Cache key to retrieve"},
                "tier": {
                    "type": "string",
                    "enum": ["memory", "disk", "both"],
                    "default": "both",
                    "description": "Which cache tier to check"
                }
            },
            "required": ["key"]
        }
    },
    {
        "name": "cache_set",
        "description": "Store a value in cache with automatic TTL based on data type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Cache key"},
                "value": {"description": "Value to cache (any JSON-serializable type)"},
                "data_type": {
                    "type": "string",
                    "enum": ["intent", "enrichment", "company", "contact", "api_response", "template", "default"],
                    "default": "default",
                    "description": "Data type for TTL configuration"
                },
                "tier": {
                    "type": "string",
                    "enum": ["memory", "disk", "both"],
                    "default": "both",
                    "description": "Which cache tier to use"
                },
                "ttl_seconds": {
                    "type": "integer",
                    "description": "Optional custom TTL in seconds"
                }
            },
            "required": ["key", "value"]
        }
    },
    {
        "name": "cache_invalidate",
        "description": "Invalidate cache entries by key, pattern, or data type.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Specific key to invalidate"},
                "pattern": {"type": "string", "description": "Pattern to match keys (substring)"},
                "data_type": {"type": "string", "description": "Invalidate all entries of this type"},
                "tier": {
                    "type": "string",
                    "enum": ["memory", "disk", "both"],
                    "default": "both"
                }
            }
        }
    },
    {
        "name": "cache_stats",
        "description": "Get cache statistics including hit rates, sizes, and cost analysis.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "cache_warm",
        "description": "Pre-warm cache with common data patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "patterns": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "value": {},
                            "data_type": {"type": "string"}
                        },
                        "required": ["key", "value"]
                    }
                }
            },
            "required": ["patterns"]
        }
    }
]


async def main():
    parser = argparse.ArgumentParser(description="Cache MCP Server")
    parser.add_argument("--dry-run", action="store_true", help="Run without making changes")
    args = parser.parse_args()
    
    global DRY_RUN
    DRY_RUN = args.dry_run
    
    if not MCP_AVAILABLE:
        print("MCP package not available. Install with: pip install mcp")
        return
    
    server = Server("cache-mcp")
    cache_server = CacheMCPServer(dry_run=DRY_RUN)
    
    if DRY_RUN:
        logger.info("Running in DRY-RUN mode")
    
    @server.list_tools()
    async def list_tools():
        return [Tool(**tool) for tool in TOOLS]
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        try:
            if name == "cache_get":
                result = await cache_server.cache_get(
                    arguments["key"],
                    arguments.get("tier", "both")
                )
            elif name == "cache_set":
                result = await cache_server.cache_set(
                    arguments["key"],
                    arguments["value"],
                    arguments.get("data_type", "default"),
                    arguments.get("tier", "both"),
                    arguments.get("ttl_seconds")
                )
            elif name == "cache_invalidate":
                result = await cache_server.cache_invalidate(
                    arguments.get("key"),
                    arguments.get("pattern"),
                    arguments.get("data_type"),
                    arguments.get("tier", "both")
                )
            elif name == "cache_stats":
                result = await cache_server.cache_stats()
            elif name == "cache_warm":
                result = await cache_server.cache_warm(arguments["patterns"])
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
