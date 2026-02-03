#!/usr/bin/env python3
"""
Supabase MCP Server - Unified Data Layer for Revenue Swarm

Provides database operations for the multi-agent system including:
- CRUD operations on all tables
- Vector search for semantic queries (pgvector)
- Stored procedure calls
- Batch operations

Tables:
- leads: All lead data (replaces .hive-mind/scraped/, enriched/, segmented/)
- outcomes: Campaign outcomes for self-annealing feedback loops
- q_table: RL Q-values for state-action pairs
- campaigns: Generated campaigns and their configurations
- patterns: Detected success/failure patterns from outcomes
- audit_log: All operations for compliance and debugging
"""

import os
import sys
import json
import logging
import time
from typing import Any, Optional
from datetime import datetime
from functools import wraps

from supabase import create_client, Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("supabase-mcp")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

MAX_RETRIES = 3
RETRY_DELAY = 1.0
TOKENS_PER_CHAR = 0.25


def retry_on_error(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """Decorator for automatic retry on transient errors."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    transient = any(x in error_str for x in [
                        "timeout", "connection", "temporarily", "retry", "503", "502"
                    ])
                    if transient and attempt < max_retries - 1:
                        wait_time = delay * (2 ** attempt)
                        logger.warning(f"Transient error, retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
                    else:
                        raise
            raise last_error
        return wrapper
    return decorator


class SupabaseClient:
    """Wrapper around Supabase client with retry logic and utilities."""
    
    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self._client: Optional[Client] = None
        self._connected = False
    
    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = create_client(self.url, self.key)
            self._connected = True
            logger.info("Supabase client initialized")
        return self._client
    
    def is_connected(self) -> bool:
        return self._connected
    
    @retry_on_error()
    def execute_query(self, table: str, operation: str, **kwargs) -> dict:
        """Execute a query with automatic retry."""
        query = self.client.table(table)
        
        if operation == "select":
            query = query.select(kwargs.get("columns", "*"))
            if kwargs.get("filters"):
                for f in kwargs["filters"]:
                    query = query.filter(f["column"], f["operator"], f["value"])
            if kwargs.get("limit"):
                query = query.limit(kwargs["limit"])
            if kwargs.get("order"):
                query = query.order(kwargs["order"]["column"], 
                                   desc=kwargs["order"].get("desc", False))
        elif operation == "insert":
            query = query.insert(kwargs["data"])
        elif operation == "upsert":
            query = query.upsert(kwargs["data"])
        elif operation == "update":
            query = query.update(kwargs["data"])
            if kwargs.get("filters"):
                for f in kwargs["filters"]:
                    query = query.filter(f["column"], f["operator"], f["value"])
        elif operation == "delete":
            query = query.delete()
            if kwargs.get("filters"):
                for f in kwargs["filters"]:
                    query = query.filter(f["column"], f["operator"], f["value"])
        
        return query.execute()
    
    @retry_on_error()
    def rpc(self, function_name: str, params: dict = None) -> dict:
        """Call a stored procedure."""
        return self.client.rpc(function_name, params or {}).execute()
    
    @staticmethod
    def estimate_tokens(data: Any) -> int:
        """Estimate token count for a result set."""
        json_str = json.dumps(data) if not isinstance(data, str) else data
        return int(len(json_str) * TOKENS_PER_CHAR)


class SupabaseMCPServer:
    """MCP Server providing Supabase database operations."""
    
    def __init__(self, url: str, key: str, dry_run: bool = False):
        self.db = SupabaseClient(url, key)
        self.dry_run = dry_run
        logger.info(f"SupabaseMCPServer initialized (dry_run={dry_run})")
    
    def _log_operation(self, operation: str, table: str, details: dict):
        """Log operation to audit_log table."""
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would log: {operation} on {table}")
            return
        
        try:
            self.db.client.table("audit_log").insert({
                "operation": operation,
                "table_name": table,
                "details": json.dumps(details),
                "timestamp": datetime.utcnow().isoformat(),
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to log operation: {e}")
    
    def db_insert(self, table: str, data: dict | list) -> dict:
        """
        Insert record(s) into any table.
        
        Args:
            table: Table name
            data: Single record dict or list of records for batch insert
        
        Returns:
            Inserted record(s) with generated IDs
        """
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would insert into {table}: {json.dumps(data)[:200]}")
            return {"dry_run": True, "would_insert": data}
        
        result = self.db.execute_query(table, "insert", data=data)
        self._log_operation("insert", table, {"count": len(data) if isinstance(data, list) else 1})
        
        logger.info(f"Inserted {len(result.data)} record(s) into {table}")
        return {
            "success": True,
            "data": result.data,
            "count": len(result.data),
            "estimated_tokens": self.db.estimate_tokens(result.data)
        }
    
    def db_upsert(self, table: str, data: dict | list, on_conflict: str = "id") -> dict:
        """
        Upsert record(s) - insert or update on conflict.
        
        Args:
            table: Table name
            data: Single record dict or list of records
            on_conflict: Column(s) to check for conflicts
        
        Returns:
            Upserted record(s)
        """
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would upsert into {table}: {json.dumps(data)[:200]}")
            return {"dry_run": True, "would_upsert": data}
        
        result = self.db.execute_query(table, "upsert", data=data)
        self._log_operation("upsert", table, {"count": len(data) if isinstance(data, list) else 1})
        
        logger.info(f"Upserted {len(result.data)} record(s) into {table}")
        return {
            "success": True,
            "data": result.data,
            "count": len(result.data),
            "estimated_tokens": self.db.estimate_tokens(result.data)
        }
    
    def db_select(
        self,
        table: str,
        columns: str = "*",
        filters: list[dict] = None,
        limit: int = None,
        order: dict = None
    ) -> dict:
        """
        Query records with optional filters.
        
        Args:
            table: Table name
            columns: Columns to select (default "*")
            filters: List of {"column": str, "operator": str, "value": any}
                     Operators: eq, neq, gt, gte, lt, lte, like, ilike, in, is
            limit: Max records to return
            order: {"column": str, "desc": bool}
        
        Returns:
            Matching records
        """
        result = self.db.execute_query(
            table, "select",
            columns=columns,
            filters=filters or [],
            limit=limit,
            order=order
        )
        
        logger.info(f"Selected {len(result.data)} record(s) from {table}")
        return {
            "success": True,
            "data": result.data,
            "count": len(result.data),
            "estimated_tokens": self.db.estimate_tokens(result.data)
        }
    
    def db_update(self, table: str, data: dict, filters: list[dict]) -> dict:
        """
        Update records matching filters.
        
        Args:
            table: Table name
            data: Fields to update
            filters: List of {"column": str, "operator": str, "value": any}
        
        Returns:
            Updated record(s)
        """
        if not filters:
            raise ValueError("Filters required for update to prevent accidental full-table update")
        
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would update {table} with filters {filters}")
            return {"dry_run": True, "would_update": data, "filters": filters}
        
        result = self.db.execute_query(table, "update", data=data, filters=filters)
        self._log_operation("update", table, {"filters": filters, "fields": list(data.keys())})
        
        logger.info(f"Updated {len(result.data)} record(s) in {table}")
        return {
            "success": True,
            "data": result.data,
            "count": len(result.data),
            "estimated_tokens": self.db.estimate_tokens(result.data)
        }
    
    def db_delete(self, table: str, filters: list[dict]) -> dict:
        """
        Delete records matching filters.
        
        Args:
            table: Table name
            filters: List of {"column": str, "operator": str, "value": any}
        
        Returns:
            Deleted record(s)
        """
        if not filters:
            raise ValueError("Filters required for delete to prevent accidental full-table delete")
        
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would delete from {table} with filters {filters}")
            return {"dry_run": True, "would_delete_filters": filters}
        
        result = self.db.execute_query(table, "delete", filters=filters)
        self._log_operation("delete", table, {"filters": filters, "count": len(result.data)})
        
        logger.info(f"Deleted {len(result.data)} record(s) from {table}")
        return {
            "success": True,
            "data": result.data,
            "count": len(result.data)
        }
    
    def db_rpc(self, function_name: str, params: dict = None) -> dict:
        """
        Call a stored procedure.
        
        Args:
            function_name: Name of the Postgres function
            params: Parameters to pass to the function
        
        Returns:
            Function result
        """
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would call RPC {function_name}({params})")
            return {"dry_run": True, "would_call": function_name, "params": params}
        
        result = self.db.rpc(function_name, params)
        self._log_operation("rpc", function_name, {"params": params})
        
        logger.info(f"Called RPC {function_name}")
        return {
            "success": True,
            "data": result.data,
            "estimated_tokens": self.db.estimate_tokens(result.data)
        }
    
    def vector_search(
        self,
        table: str,
        embedding_column: str,
        query_embedding: list[float],
        match_threshold: float = 0.7,
        match_count: int = 10,
        filter_column: str = None,
        filter_value: Any = None
    ) -> dict:
        """
        Semantic search using pgvector.
        
        Args:
            table: Table with embeddings
            embedding_column: Column containing vectors
            query_embedding: Query vector
            match_threshold: Minimum similarity (0-1)
            match_count: Max results
            filter_column: Optional column to filter on
            filter_value: Value for filter column
        
        Returns:
            Matching records with similarity scores
        """
        params = {
            "query_embedding": query_embedding,
            "match_threshold": match_threshold,
            "match_count": match_count,
            "table_name": table,
            "embedding_column": embedding_column,
        }
        
        if filter_column and filter_value is not None:
            params["filter_column"] = filter_column
            params["filter_value"] = filter_value
        
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would perform vector search on {table}.{embedding_column}")
            return {"dry_run": True, "params": params}
        
        result = self.db.rpc("match_vectors", params)
        
        logger.info(f"Vector search returned {len(result.data)} results")
        return {
            "success": True,
            "data": result.data,
            "count": len(result.data),
            "estimated_tokens": self.db.estimate_tokens(result.data)
        }
    
    def batch_insert(self, table: str, records: list[dict], batch_size: int = 100) -> dict:
        """
        Batch insert with chunking for large datasets.
        
        Args:
            table: Table name
            records: List of records to insert
            batch_size: Records per batch
        
        Returns:
            Summary of inserted records
        """
        if self.dry_run:
            logger.info(f"[DRY-RUN] Would batch insert {len(records)} records into {table}")
            return {"dry_run": True, "would_insert_count": len(records)}
        
        total_inserted = 0
        all_data = []
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            result = self.db.execute_query(table, "insert", data=batch)
            total_inserted += len(result.data)
            all_data.extend(result.data)
            logger.info(f"Batch {i // batch_size + 1}: inserted {len(result.data)} records")
        
        self._log_operation("batch_insert", table, {"total_count": total_inserted})
        
        return {
            "success": True,
            "total_inserted": total_inserted,
            "batches": (len(records) + batch_size - 1) // batch_size,
            "estimated_tokens": self.db.estimate_tokens(all_data)
        }
    
    def list_tables(self) -> dict:
        """List all tables in the public schema."""
        result = self.db.rpc("get_tables", {})
        return {"tables": result.data}
    
    def health_check(self) -> dict:
        """Check database connectivity."""
        try:
            result = self.db.client.table("audit_log").select("id").limit(1).execute()
            return {
                "status": "healthy",
                "connected": True,
                "dry_run": self.dry_run
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }


def get_tools() -> list[dict]:
    """Return MCP tool definitions."""
    return [
        {
            "name": "db_insert",
            "description": "Insert record(s) into a Supabase table",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "table": {"type": "string", "description": "Table name"},
                    "data": {"type": ["object", "array"], "description": "Record or list of records"}
                },
                "required": ["table", "data"]
            }
        },
        {
            "name": "db_upsert",
            "description": "Upsert record(s) - insert or update on conflict",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "data": {"type": ["object", "array"]},
                    "on_conflict": {"type": "string", "default": "id"}
                },
                "required": ["table", "data"]
            }
        },
        {
            "name": "db_select",
            "description": "Query records with optional filters",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "columns": {"type": "string", "default": "*"},
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {"type": "string"},
                                "operator": {"type": "string"},
                                "value": {}
                            }
                        }
                    },
                    "limit": {"type": "integer"},
                    "order": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "desc": {"type": "boolean"}
                        }
                    }
                },
                "required": ["table"]
            }
        },
        {
            "name": "db_update",
            "description": "Update records matching filters",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "data": {"type": "object"},
                    "filters": {"type": "array"}
                },
                "required": ["table", "data", "filters"]
            }
        },
        {
            "name": "db_delete",
            "description": "Delete records matching filters",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "filters": {"type": "array"}
                },
                "required": ["table", "filters"]
            }
        },
        {
            "name": "db_rpc",
            "description": "Call a stored procedure",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "function_name": {"type": "string"},
                    "params": {"type": "object"}
                },
                "required": ["function_name"]
            }
        },
        {
            "name": "vector_search",
            "description": "Semantic search using pgvector embeddings",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "embedding_column": {"type": "string"},
                    "query_embedding": {"type": "array", "items": {"type": "number"}},
                    "match_threshold": {"type": "number", "default": 0.7},
                    "match_count": {"type": "integer", "default": 10},
                    "filter_column": {"type": "string"},
                    "filter_value": {}
                },
                "required": ["table", "embedding_column", "query_embedding"]
            }
        }
    ]


if __name__ == "__main__":
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: SUPABASE_URL and SUPABASE_KEY environment variables required")
        sys.exit(1)
    
    server = SupabaseMCPServer(SUPABASE_URL, SUPABASE_KEY, dry_run=DRY_RUN)
    
    print("Testing Supabase connection...")
    health = server.health_check()
    print(f"Health check: {json.dumps(health, indent=2)}")
    
    if health["connected"]:
        print("\nAvailable tools:")
        for tool in get_tools():
            print(f"  - {tool['name']}: {tool['description']}")
    else:
        print("Connection failed. Check your credentials.")
        sys.exit(1)
