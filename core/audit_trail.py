"""
Comprehensive Audit Trail System for Agent Actions.

Day 18 Implementation:
- SQLite primary storage (.hive-mind/audit.db)
- JSON backup with daily snapshots
- 90-day retention with automatic cleanup
- Query API for logs, stats, and search
- Weekly markdown reports
- PII redaction for sensitive data
- Support for all 13 Beta Swarm agents
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import re
import sqlite3
import asyncio
import aiosqlite
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict
from enum import Enum

PROJECT_ROOT = Path(__file__).parent.parent
HIVE_MIND_DIR = PROJECT_ROOT / ".hive-mind"
DEFAULT_DB_PATH = HIVE_MIND_DIR / "audit.db"
DEFAULT_BACKUP_DIR = HIVE_MIND_DIR / "audit_backup"


# ============================================================================
# PII REDACTION
# ============================================================================

class PIIType(Enum):
    """Types of PII that can be redacted."""
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    NAME = "name"
    ADDRESS = "address"
    API_KEY = "api_key"


class PIIRedactor:
    """
    Redacts Personally Identifiable Information from text and data structures.
    
    Detects and masks:
    - Email addresses
    - Phone numbers
    - SSN (Social Security Numbers)
    - Credit card numbers
    - IP addresses
    - API keys/tokens
    - Custom patterns
    """
    
    # Regex patterns for PII detection
    PATTERNS = {
        PIIType.EMAIL: re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        ),
        PIIType.PHONE: re.compile(
            r'(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}'
        ),
        PIIType.SSN: re.compile(
            r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b'
        ),
        PIIType.CREDIT_CARD: re.compile(
            r'\b(?:\d{4}[-.\s]?){3}\d{4}\b'
        ),
        PIIType.IP_ADDRESS: re.compile(
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        ),
        PIIType.API_KEY: re.compile(
            r'(?:api[_-]?key|token|secret|password|auth)["\']?\s*[:=]\s*["\']?([A-Za-z0-9_\-]{20,})["\']?',
            re.IGNORECASE
        ),
    }
    
    # Default redaction masks
    MASKS = {
        PIIType.EMAIL: "[EMAIL_REDACTED]",
        PIIType.PHONE: "[PHONE_REDACTED]",
        PIIType.SSN: "[SSN_REDACTED]",
        PIIType.CREDIT_CARD: "[CC_REDACTED]",
        PIIType.IP_ADDRESS: "[IP_REDACTED]",
        PIIType.API_KEY: "[API_KEY_REDACTED]",
        PIIType.NAME: "[NAME_REDACTED]",
        PIIType.ADDRESS: "[ADDRESS_REDACTED]",
    }
    
    # Sensitive field names that should be fully redacted
    SENSITIVE_FIELDS: Set[str] = {
        "password", "secret", "token", "api_key", "apikey", "auth", "authorization",
        "credit_card", "creditcard", "cc_number", "ssn", "social_security",
        "bank_account", "routing_number", "private_key", "access_token",
        "refresh_token", "bearer", "credential"
    }
    
    @classmethod
    def redact_string(cls, text: str, preserve_partial: bool = False) -> str:
        """
        Redact PII from a string.
        
        Args:
            text: String to redact
            preserve_partial: If True, show partial data (e.g., email domain)
        
        Returns:
            Redacted string
        """
        if not isinstance(text, str):
            return str(text)
        
        result = text
        
        # Redact each PII type
        for pii_type, pattern in cls.PATTERNS.items():
            if pii_type == PIIType.EMAIL and preserve_partial:
                # Show domain only: user@domain.com -> [REDACTED]@domain.com
                result = pattern.sub(
                    lambda m: f"[REDACTED]@{m.group().split('@')[1]}", 
                    result
                )
            elif pii_type == PIIType.API_KEY:
                # Special handling for API keys in key=value format
                result = re.sub(
                    cls.PATTERNS[PIIType.API_KEY],
                    lambda m: m.group().replace(m.group(1), cls.MASKS[pii_type]) if m.group(1) else m.group(),
                    result
                )
            else:
                result = pattern.sub(cls.MASKS[pii_type], result)
        
        return result
    
    @classmethod
    def redact_dict(cls, data: Dict[str, Any], depth: int = 0, max_depth: int = 10) -> Dict[str, Any]:
        """
        Recursively redact PII from a dictionary.
        
        Args:
            data: Dictionary to redact
            depth: Current recursion depth
            max_depth: Maximum recursion depth
        
        Returns:
            Redacted dictionary
        """
        if depth > max_depth:
            return {"_truncated": "max_depth_exceeded"}
        
        if not isinstance(data, dict):
            return data
        
        result = {}
        
        for key, value in data.items():
            key_lower = key.lower().replace("-", "_")
            
            # Check if field name indicates sensitive data
            if any(sensitive in key_lower for sensitive in cls.SENSITIVE_FIELDS):
                result[key] = "[SENSITIVE_REDACTED]"
            elif isinstance(value, dict):
                result[key] = cls.redact_dict(value, depth + 1, max_depth)
            elif isinstance(value, list):
                result[key] = [
                    cls.redact_dict(item, depth + 1, max_depth) if isinstance(item, dict)
                    else cls.redact_string(str(item)) if isinstance(item, str)
                    else item
                    for item in value
                ]
            elif isinstance(value, str):
                result[key] = cls.redact_string(value)
            else:
                result[key] = value
        
        return result
    
    @classmethod
    def create_summary(cls, data: Dict[str, Any], max_length: int = 500) -> str:
        """
        Create a redacted summary of input/output data.
        
        Args:
            data: Data to summarize
            max_length: Maximum length of summary
        
        Returns:
            Redacted, truncated summary string
        """
        redacted = cls.redact_dict(data)
        summary = json.dumps(redacted, default=str)
        
        if len(summary) > max_length:
            return summary[:max_length - 3] + "..."
        
        return summary


class ApprovalStatus(Enum):
    """Status of action approval."""
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"
    ESCALATED = "escalated"
    NOT_REQUIRED = "not_required"


@dataclass
class AuditEntry:
    """
    Represents a single audit log entry.
    
    Day 18 fields:
    - timestamp: ISO format datetime
    - agent_name: Name of the agent (agent_id)
    - action_type: Type of action performed
    - target_resource: Resource being acted upon
    - action_details: Full action details (input/output)
    - input_summary: Redacted summary of input
    - output_summary: Redacted summary of output
    - status: success/failure/pending
    - approval_status: Approval state of the action
    - risk_level: LOW/MEDIUM/HIGH/CRITICAL
    - grounding_evidence: Evidence for action justification
    - duration_ms: Execution time in milliseconds
    - error_message: Error details if failed
    """
    timestamp: str
    agent_name: str
    action_type: str
    target_resource: str  # New: Resource being acted upon
    action_details: Dict[str, Any]
    input_summary: str  # New: Redacted input summary
    output_summary: str  # New: Redacted output summary
    status: str  # "success", "failure", "pending"
    approval_status: str  # New: ApprovalStatus value
    risk_level: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    grounding_evidence: Optional[Dict[str, Any]] = None
    duration_ms: Optional[float] = None
    error_message: Optional[str] = None
    id: Optional[int] = None



class AuditTrail:
    """
    Comprehensive audit trail system with SQLite storage, JSON backup,
    and retention policies.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        backup_dir: Optional[Path] = None
    ):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.backup_dir = backup_dir or DEFAULT_BACKUP_DIR
        self._write_lock = asyncio.Lock()
        self._initialized = False
        self._cleanup_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """Initialize database tables and backup directory."""
        if self._initialized:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(str(self.db_path)) as db:
            # Main audit log table with Day 18 enhancements
            await db.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    target_resource TEXT,
                    action_details TEXT NOT NULL,
                    input_summary TEXT,
                    output_summary TEXT,
                    status TEXT NOT NULL,
                    approval_status TEXT,
                    risk_level TEXT NOT NULL,
                    grounding_evidence TEXT,
                    duration_ms REAL,
                    error_message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Add new columns if they don't exist (for migration)
            try:
                await db.execute("ALTER TABLE audit_log ADD COLUMN target_resource TEXT")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE audit_log ADD COLUMN input_summary TEXT")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE audit_log ADD COLUMN output_summary TEXT")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE audit_log ADD COLUMN approval_status TEXT")
            except Exception:
                pass

            await db.execute("""
                CREATE TABLE IF NOT EXISTS audit_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    total_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    avg_duration_ms REAL,
                    UNIQUE(date, agent_name, action_type)
                )
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp 
                ON audit_log(timestamp)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_agent 
                ON audit_log(agent_name)
            """)
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_action 
                ON audit_log(action_type)
            """)

            await db.commit()

        self._initialized = True

    async def close(self) -> None:
        """Clean up resources."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def log_action(
        self,
        agent_name: str,
        action_type: str,
        details: Dict[str, Any],
        status: str,
        risk_level: str,
        target_resource: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        approval_status: str = "not_required",
        grounding_evidence: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
        redact_pii: bool = True
    ) -> int:
        """
        Log an agent action to the audit trail.
        
        Args:
            agent_name: Name of the agent performing the action
            action_type: Type of action (e.g., "scrape", "enrich", "email")
            details: Full action details
            status: "success", "failure", or "pending"
            risk_level: "LOW", "MEDIUM", "HIGH", "CRITICAL"
            target_resource: Resource being acted upon (e.g., lead email, API endpoint)
            input_data: Input data for the action (will be redacted)
            output_data: Output data from the action (will be redacted)
            approval_status: ApprovalStatus value
            grounding_evidence: Evidence supporting the action
            duration_ms: Execution time in milliseconds
            error: Error message if failed
            redact_pii: Whether to redact PII (default True)

        Returns:
            The ID of the created audit log entry.
        """
        await self.initialize()

        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Create redacted summaries for input/output
        input_summary = ""
        output_summary = ""
        
        if input_data:
            if redact_pii:
                input_summary = PIIRedactor.create_summary(input_data)
            else:
                input_summary = json.dumps(input_data, default=str)[:500]
        
        if output_data:
            if redact_pii:
                output_summary = PIIRedactor.create_summary(output_data)
            else:
                output_summary = json.dumps(output_data, default=str)[:500]
        
        # Redact details if needed
        if redact_pii:
            details = PIIRedactor.redact_dict(details)
        
        # Redact target_resource if it looks like PII
        if target_resource and redact_pii:
            target_resource = PIIRedactor.redact_string(target_resource)
        
        entry = AuditEntry(
            timestamp=timestamp,
            agent_name=agent_name,
            action_type=action_type,
            target_resource=target_resource or "",
            action_details=details,
            input_summary=input_summary,
            output_summary=output_summary,
            status=status,
            approval_status=approval_status,
            risk_level=risk_level,
            grounding_evidence=grounding_evidence,
            duration_ms=duration_ms,
            error_message=error
        )

        async with self._write_lock:
            async with aiosqlite.connect(str(self.db_path)) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO audit_log 
                    (timestamp, agent_name, action_type, target_resource, action_details,
                     input_summary, output_summary, status, approval_status, risk_level,
                     grounding_evidence, duration_ms, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.timestamp,
                        entry.agent_name,
                        entry.action_type,
                        entry.target_resource,
                        json.dumps(entry.action_details),
                        entry.input_summary,
                        entry.output_summary,
                        entry.status,
                        entry.approval_status,
                        entry.risk_level,
                        json.dumps(entry.grounding_evidence) if entry.grounding_evidence else None,
                        entry.duration_ms,
                        entry.error_message
                    )
                )
                entry_id = cursor.lastrowid
                await self._update_metrics(db, entry)
                await db.commit()

        return entry_id

    async def _update_metrics(
        self,
        db: aiosqlite.Connection,
        entry: AuditEntry
    ) -> None:
        """Update aggregated metrics for the entry."""
        date = entry.timestamp[:10]  # YYYY-MM-DD

        await db.execute(
            """
            INSERT INTO audit_metrics (date, agent_name, action_type, 
                                        total_count, success_count, failure_count, avg_duration_ms)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(date, agent_name, action_type) DO UPDATE SET
                total_count = total_count + 1,
                success_count = success_count + ?,
                failure_count = failure_count + ?,
                avg_duration_ms = CASE 
                    WHEN excluded.avg_duration_ms IS NOT NULL 
                    THEN (COALESCE(avg_duration_ms, 0) * total_count + excluded.avg_duration_ms) / (total_count + 1)
                    ELSE avg_duration_ms
                END
            """,
            (
                date,
                entry.agent_name,
                entry.action_type,
                1 if entry.status == "success" else 0,
                1 if entry.status == "failure" else 0,
                entry.duration_ms,
                1 if entry.status == "success" else 0,
                1 if entry.status == "failure" else 0
            )
        )

    async def get_logs(
        self,
        agent_name: Optional[str] = None,
        action_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query audit logs with optional filters.

        Args:
            agent_name: Filter by agent name
            action_type: Filter by action type
            start_date: Filter by start date (ISO format)
            end_date: Filter by end date (ISO format)
            limit: Maximum number of results

        Returns:
            List of audit log entries as dictionaries.
        """
        await self.initialize()

        conditions = []
        params = []

        if agent_name:
            conditions.append("agent_name = ?")
            params.append(agent_name)
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)
        if start_date:
            conditions.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("timestamp <= ?")
            params.append(end_date)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT * FROM audit_log 
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                params
            )
            rows = await cursor.fetchall()

        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: aiosqlite.Row) -> Dict[str, Any]:
        """Convert a database row to a dictionary."""
        result = dict(row)
        if result.get("action_details"):
            result["action_details"] = json.loads(result["action_details"])
        if result.get("grounding_evidence"):
            result["grounding_evidence"] = json.loads(result["grounding_evidence"])
        return result

    async def get_agent_stats(
        self,
        agent_name: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get statistics for a specific agent over the past N days.

        Returns:
            Dictionary with success_rate, avg_duration, and action_counts.
        """
        await self.initialize()

        start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """
                SELECT 
                    SUM(total_count) as total,
                    SUM(success_count) as successes,
                    SUM(failure_count) as failures,
                    AVG(avg_duration_ms) as avg_duration
                FROM audit_metrics
                WHERE agent_name = ? AND date >= ?
                """,
                (agent_name, start_date)
            )
            row = await cursor.fetchone()

            total = row["total"] or 0
            successes = row["successes"] or 0
            success_rate = (successes / total * 100) if total > 0 else 0.0

            cursor = await db.execute(
                """
                SELECT action_type, SUM(total_count) as count
                FROM audit_metrics
                WHERE agent_name = ? AND date >= ?
                GROUP BY action_type
                """,
                (agent_name, start_date)
            )
            action_rows = await cursor.fetchall()
            action_counts = {r["action_type"]: r["count"] for r in action_rows}

        return {
            "success_rate": round(success_rate, 2),
            "avg_duration": round(row["avg_duration"] or 0, 2),
            "action_counts": action_counts,
            "total_actions": total,
            "successes": successes,
            "failures": row["failures"] or 0
        }

    async def get_daily_summary(
        self,
        date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get a summary of all actions for a specific date.

        Args:
            date: Date in YYYY-MM-DD format. Defaults to today.

        Returns:
            Dictionary with totals by agent and action type.
        """
        await self.initialize()

        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """
                SELECT 
                    agent_name,
                    action_type,
                    SUM(total_count) as total,
                    SUM(success_count) as successes,
                    SUM(failure_count) as failures,
                    AVG(avg_duration_ms) as avg_duration
                FROM audit_metrics
                WHERE date = ?
                GROUP BY agent_name, action_type
                """,
                (date,)
            )
            rows = await cursor.fetchall()

        by_agent = defaultdict(lambda: {"total": 0, "successes": 0, "failures": 0, "actions": {}})
        by_action_type = defaultdict(lambda: {"total": 0, "successes": 0, "failures": 0})

        for row in rows:
            agent = row["agent_name"]
            action = row["action_type"]

            by_agent[agent]["total"] += row["total"]
            by_agent[agent]["successes"] += row["successes"]
            by_agent[agent]["failures"] += row["failures"]
            by_agent[agent]["actions"][action] = {
                "total": row["total"],
                "successes": row["successes"],
                "failures": row["failures"],
                "avg_duration": round(row["avg_duration"] or 0, 2)
            }

            by_action_type[action]["total"] += row["total"]
            by_action_type[action]["successes"] += row["successes"]
            by_action_type[action]["failures"] += row["failures"]

        total_actions = sum(a["total"] for a in by_agent.values())
        total_successes = sum(a["successes"] for a in by_agent.values())
        total_failures = sum(a["failures"] for a in by_agent.values())

        return {
            "date": date,
            "total_actions": total_actions,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "success_rate": round((total_successes / total_actions * 100) if total_actions > 0 else 0, 2),
            "by_agent": dict(by_agent),
            "by_action_type": dict(by_action_type)
        }

    async def search_logs(
        self,
        query_text: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Full-text search in action_details.

        Args:
            query_text: Text to search for
            limit: Maximum number of results

        Returns:
            List of matching audit log entries.
        """
        await self.initialize()

        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM audit_log 
                WHERE action_details LIKE ?
                   OR error_message LIKE ?
                   OR agent_name LIKE ?
                   OR action_type LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (f"%{query_text}%", f"%{query_text}%", 
                 f"%{query_text}%", f"%{query_text}%", limit)
            )
            rows = await cursor.fetchall()

        return [self._row_to_dict(row) for row in rows]

    async def generate_weekly_report(self) -> str:
        """
        Generate a markdown weekly report.

        Returns:
            Markdown-formatted report string.
        """
        await self.initialize()

        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=7)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row

            cursor = await db.execute(
                """
                SELECT 
                    agent_name,
                    SUM(total_count) as total,
                    SUM(success_count) as successes,
                    SUM(failure_count) as failures
                FROM audit_metrics
                WHERE date >= ? AND date <= ?
                GROUP BY agent_name
                ORDER BY total DESC
                """,
                (start_str, end_str)
            )
            agent_stats = await cursor.fetchall()

            cursor = await db.execute(
                """
                SELECT 
                    action_type,
                    AVG(avg_duration_ms) as avg_duration,
                    SUM(total_count) as total
                FROM audit_metrics
                WHERE date >= ? AND date <= ?
                GROUP BY action_type
                ORDER BY total DESC
                """,
                (start_str, end_str)
            )
            latency_stats = await cursor.fetchall()

            cursor = await db.execute(
                """
                SELECT error_message, COUNT(*) as count
                FROM audit_log
                WHERE timestamp >= ? AND timestamp <= ?
                  AND status = 'failure'
                  AND error_message IS NOT NULL
                GROUP BY error_message
                ORDER BY count DESC
                LIMIT 10
                """,
                (start_str, end_str)
            )
            top_errors = await cursor.fetchall()

            cursor = await db.execute(
                """
                SELECT risk_level, COUNT(*) as count
                FROM audit_log
                WHERE timestamp >= ? AND timestamp <= ?
                GROUP BY risk_level
                ORDER BY 
                    CASE risk_level 
                        WHEN 'CRITICAL' THEN 1 
                        WHEN 'HIGH' THEN 2 
                        WHEN 'MEDIUM' THEN 3 
                        WHEN 'LOW' THEN 4 
                    END
                """,
                (start_str, end_str)
            )
            risk_dist = await cursor.fetchall()

        total_actions = sum(r["total"] for r in agent_stats)
        total_successes = sum(r["successes"] for r in agent_stats)
        total_failures = sum(r["failures"] for r in agent_stats)
        overall_success_rate = (total_successes / total_actions * 100) if total_actions > 0 else 0

        report = f"""# Weekly Audit Report

**Period:** {start_str} to {end_str}

## Summary

- **Total Actions:** {total_actions}
- **Success Rate:** {overall_success_rate:.1f}%
- **Total Successes:** {total_successes}
- **Total Failures:** {total_failures}

## Actions by Agent

| Agent | Total | Successes | Failures | Success Rate |
|-------|-------|-----------|----------|--------------|
"""
        for row in agent_stats:
            rate = (row["successes"] / row["total"] * 100) if row["total"] > 0 else 0
            report += f"| {row['agent_name']} | {row['total']} | {row['successes']} | {row['failures']} | {rate:.1f}% |\n"

        report += """
## Average Latency by Action Type

| Action Type | Avg Duration (ms) | Count |
|-------------|-------------------|-------|
"""
        for row in latency_stats:
            avg_dur = row['avg_duration'] if row['avg_duration'] is not None else 0
            report += f"| {row['action_type']} | {avg_dur:.2f} | {row['total']} |\n"

        report += """
## Top 10 Errors

| Error | Count |
|-------|-------|
"""
        for row in top_errors:
            error_msg = (row["error_message"][:50] + "...") if len(row["error_message"]) > 50 else row["error_message"]
            report += f"| {error_msg} | {row['count']} |\n"

        report += """
## Risk Level Distribution

| Risk Level | Count |
|------------|-------|
"""
        for row in risk_dist:
            report += f"| {row['risk_level']} | {row['count']} |\n"

        return report

    async def create_daily_backup(self) -> Path:
        """
        Create a JSON backup of today's audit logs.

        Returns:
            Path to the created backup file.
        """
        await self.initialize()

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        backup_file = self.backup_dir / f"{today}.json"

        logs = await self.get_logs(
            start_date=today,
            end_date=today + "T23:59:59Z",
            limit=100000
        )

        async with self._write_lock:
            with open(backup_file, "w") as f:
                json.dump({
                    "date": today,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(logs),
                    "logs": logs
                }, f, indent=2, default=str)

        return backup_file

    async def run_retention_cleanup(self) -> Dict[str, int]:
        """
        Clean up records older than 90 days.

        Returns:
            Dictionary with counts of deleted records and archived files.
        """
        await self.initialize()

        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        cutoff_date_short = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")

        deleted_logs = 0
        deleted_metrics = 0
        archived_files = 0

        async with self._write_lock:
            async with aiosqlite.connect(str(self.db_path)) as db:
                cursor = await db.execute(
                    "DELETE FROM audit_log WHERE timestamp < ?",
                    (cutoff_date,)
                )
                deleted_logs = cursor.rowcount

                cursor = await db.execute(
                    "DELETE FROM audit_metrics WHERE date < ?",
                    (cutoff_date_short,)
                )
                deleted_metrics = cursor.rowcount

                await db.commit()

        archive_dir = self.backup_dir / "archive"
        archive_dir.mkdir(exist_ok=True)

        for backup_file in self.backup_dir.glob("*.json"):
            try:
                file_date = backup_file.stem
                if file_date < cutoff_date_short:
                    backup_file.rename(archive_dir / backup_file.name)
                    archived_files += 1
            except (ValueError, OSError):
                continue

        return {
            "deleted_logs": deleted_logs,
            "deleted_metrics": deleted_metrics,
            "archived_files": archived_files
        }

    async def start_cleanup_job(self) -> None:
        """Start the async cleanup job that runs daily."""
        async def cleanup_loop():
            while True:
                await asyncio.sleep(86400)  # 24 hours
                try:
                    await self.run_retention_cleanup()
                    await self.create_daily_backup()
                except Exception:
                    pass

        self._cleanup_task = asyncio.create_task(cleanup_loop())


async def get_audit_trail(
    db_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None
) -> AuditTrail:
    """
    Factory function to get an initialized AuditTrail instance.
    """
    trail = AuditTrail(db_path=db_path, backup_dir=backup_dir)
    await trail.initialize()
    return trail
