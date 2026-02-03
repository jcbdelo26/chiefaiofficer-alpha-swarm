#!/usr/bin/env python3
"""
Log Parser - Unified Log Aggregation
====================================

Aggregates logs from multiple sources:
- audit.db (SQLite audit trail)
- retry_queue.jsonl (failed operations queued for retry)
- Python log files
- Frontend error logs

Provides unified search and filtering across all sources.
"""

import json
import re
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from enum import Enum
from collections import defaultdict
import logging

try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False

logger = logging.getLogger("debug-mcp.log_parser")


class LogSource(Enum):
    """Available log sources."""
    AUDIT = "audit"
    FRONTEND = "frontend"
    RETRY_QUEUE = "retry_queue"
    LOGS = "logs"


class LogParser:
    """
    Unified log parser that aggregates and searches across multiple log sources.

    Sources:
    - audit: SQLite audit trail database
    - frontend: JSONL file of browser console errors
    - retry_queue: JSONL file of failed operations queued for retry
    - logs: Python log files in the logs directory
    """

    def __init__(
        self,
        audit_db_path: Path,
        logs_dir: Path,
        retry_queue_path: Path,
        frontend_errors_path: Optional[Path] = None
    ):
        self.audit_db_path = audit_db_path
        self.logs_dir = logs_dir
        self.retry_queue_path = retry_queue_path
        self.frontend_errors_path = frontend_errors_path or (
            audit_db_path.parent / "frontend_errors.jsonl"
        )
        self._initialized = False

    async def initialize(self):
        """Initialize the log parser."""
        if self._initialized:
            return

        # Ensure directories exist
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.retry_queue_path.parent.mkdir(parents=True, exist_ok=True)

        self._initialized = True

    async def get_errors(
        self,
        source: Optional[str] = None,
        agent_name: Optional[str] = None,
        hours: int = 24,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get errors from all sources.

        Args:
            source: Filter by source (audit, frontend, retry_queue, logs)
            agent_name: Filter by agent name
            hours: Look back this many hours
            limit: Maximum number of results

        Returns:
            List of error entries with source metadata
        """
        await self.initialize()

        errors = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()

        # Get audit log errors
        if source is None or source == "audit":
            audit_errors = await self._get_audit_errors(
                agent_name=agent_name,
                cutoff=cutoff_str,
                limit=limit
            )
            errors.extend(audit_errors)

        # Get retry queue errors
        if source is None or source == "retry_queue":
            retry_errors = await self._get_retry_queue_errors(
                cutoff=cutoff,
                limit=limit
            )
            errors.extend(retry_errors)

        # Get frontend errors
        if (source is None or source == "frontend") and not agent_name:
            frontend_errors = await self._get_frontend_errors(
                cutoff=cutoff,
                limit=limit
            )
            errors.extend(frontend_errors)

        # Get Python log errors
        if source is None or source == "logs":
            log_errors = await self._get_log_file_errors(
                agent_name=agent_name,
                cutoff=cutoff,
                limit=limit
            )
            errors.extend(log_errors)

        # Sort by timestamp (newest first) and limit
        errors.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return errors[:limit]

    async def _get_audit_errors(
        self,
        agent_name: Optional[str],
        cutoff: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Get errors from audit database."""
        if not self.audit_db_path.exists():
            return []

        errors = []

        try:
            async with aiosqlite.connect(str(self.audit_db_path)) as db:
                db.row_factory = aiosqlite.Row

                query = """
                    SELECT * FROM audit_log
                    WHERE status = 'failure'
                    AND timestamp >= ?
                """
                params = [cutoff]

                if agent_name:
                    query += " AND agent_name = ?"
                    params.append(agent_name)

                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor = await db.execute(query, params)
                rows = await cursor.fetchall()

                for row in rows:
                    entry = dict(row)
                    entry["source"] = "audit"
                    entry["error_type"] = entry.get("action_type", "unknown")

                    if entry.get("action_details"):
                        try:
                            entry["action_details"] = json.loads(entry["action_details"])
                        except json.JSONDecodeError:
                            pass

                    errors.append(entry)

        except Exception as e:
            logger.warning(f"Failed to query audit log: {e}")

        return errors

    async def _get_retry_queue_errors(
        self,
        cutoff: datetime,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Get errors from retry queue."""
        if not self.retry_queue_path.exists():
            return []

        errors = []

        try:
            with open(self.retry_queue_path, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())

                        # Parse timestamp
                        ts_str = entry.get("timestamp") or entry.get("created_at", "")
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if ts < cutoff:
                                continue
                        except (ValueError, TypeError):
                            continue

                        errors.append({
                            "source": "retry_queue",
                            "timestamp": ts_str,
                            "error_type": "retry_queued",
                            "operation": entry.get("operation_name"),
                            "error_message": entry.get("last_error"),
                            "retry_count": entry.get("retry_count", 0),
                            "agent_name": entry.get("agent_name"),
                            "payload_summary": str(entry.get("payload", {}))[:200]
                        })

                        if len(errors) >= limit:
                            break

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.warning(f"Failed to read retry queue: {e}")

        return errors

    async def _get_frontend_errors(
        self,
        cutoff: datetime,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Get errors from frontend error log."""
        if not self.frontend_errors_path.exists():
            return []

        errors = []

        try:
            with open(self.frontend_errors_path, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())

                        ts_str = entry.get("timestamp", "")
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if ts < cutoff:
                                continue
                        except (ValueError, TypeError):
                            continue

                        errors.append({
                            "source": "frontend",
                            "timestamp": ts_str,
                            "error_type": entry.get("console_type", "error"),
                            "error_message": entry.get("message"),
                            "stack": entry.get("stack"),
                            "url": entry.get("url"),
                            "correlation_id": entry.get("correlation_id")
                        })

                        if len(errors) >= limit:
                            break

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.warning(f"Failed to read frontend errors: {e}")

        return errors

    async def _get_log_file_errors(
        self,
        agent_name: Optional[str],
        cutoff: datetime,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Get errors from Python log files."""
        errors = []

        # Common error patterns in Python logs
        error_pattern = re.compile(
            r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)\s*'
            r'(?:-\s*)?'
            r'(ERROR|CRITICAL|WARNING)\s*'
            r'(?:-\s*)?'
            r'(\S+)?\s*'
            r'(?:-\s*)?'
            r'(.+)',
            re.IGNORECASE
        )

        try:
            log_files = list(self.logs_dir.glob("*.log"))

            # Also check common log locations
            for extra_path in [
                self.audit_db_path.parent / "logs",
                self.audit_db_path.parent.parent / "logs"
            ]:
                if extra_path.exists():
                    log_files.extend(extra_path.glob("*.log"))

            for log_file in log_files:
                try:
                    # Skip large files
                    if log_file.stat().st_size > 10_000_000:  # 10MB
                        continue

                    with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            match = error_pattern.search(line)
                            if not match:
                                continue

                            level = match.group(2).upper()
                            if level not in ["ERROR", "CRITICAL"]:
                                continue

                            ts_str = match.group(1)
                            try:
                                # Handle various timestamp formats
                                ts_str_normalized = ts_str.replace(" ", "T")
                                if not ts_str_normalized.endswith("Z") and "+" not in ts_str_normalized:
                                    ts_str_normalized += "+00:00"
                                ts = datetime.fromisoformat(ts_str_normalized.replace("Z", "+00:00"))
                                if ts < cutoff:
                                    continue
                            except (ValueError, TypeError):
                                continue

                            logger_name = match.group(3) or "unknown"
                            message = match.group(4).strip()

                            # Filter by agent name if specified
                            if agent_name:
                                if agent_name.lower() not in logger_name.lower():
                                    continue

                            errors.append({
                                "source": "logs",
                                "timestamp": ts_str,
                                "error_type": level.lower(),
                                "logger": logger_name,
                                "error_message": message,
                                "file": str(log_file.name)
                            })

                            if len(errors) >= limit:
                                return errors

                except Exception as e:
                    logger.debug(f"Failed to parse log file {log_file}: {e}")

        except Exception as e:
            logger.warning(f"Failed to read log files: {e}")

        return errors

    async def get_audit_entry(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific audit log entry by ID."""
        if not self.audit_db_path.exists():
            return None

        try:
            async with aiosqlite.connect(str(self.audit_db_path)) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM audit_log WHERE id = ?",
                    (entry_id,)
                )
                row = await cursor.fetchone()

                if row:
                    entry = dict(row)
                    if entry.get("action_details"):
                        try:
                            entry["action_details"] = json.loads(entry["action_details"])
                        except json.JSONDecodeError:
                            pass
                    if entry.get("grounding_evidence"):
                        try:
                            entry["grounding_evidence"] = json.loads(entry["grounding_evidence"])
                        except json.JSONDecodeError:
                            pass
                    return entry

        except Exception as e:
            logger.warning(f"Failed to get audit entry {entry_id}: {e}")

        return None

    async def get_logs_around_time(
        self,
        timestamp: str,
        window_seconds: int = 30,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get logs within a time window around a specific timestamp."""
        try:
            center_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return []

        start_time = center_time - timedelta(seconds=window_seconds)
        end_time = center_time + timedelta(seconds=window_seconds)

        logs = []

        # Query audit log
        if self.audit_db_path.exists():
            try:
                async with aiosqlite.connect(str(self.audit_db_path)) as db:
                    db.row_factory = aiosqlite.Row
                    cursor = await db.execute(
                        """
                        SELECT * FROM audit_log
                        WHERE timestamp >= ? AND timestamp <= ?
                        ORDER BY timestamp ASC
                        LIMIT ?
                        """,
                        (start_time.isoformat(), end_time.isoformat(), limit)
                    )
                    rows = await cursor.fetchall()

                    for row in rows:
                        entry = dict(row)
                        entry["source"] = "audit"
                        logs.append(entry)

            except Exception as e:
                logger.warning(f"Failed to query audit log: {e}")

        # Sort by timestamp
        logs.sort(key=lambda x: x.get("timestamp", ""))

        return logs[:limit]

    async def get_by_correlation_id(
        self,
        correlation_id: str
    ) -> List[Dict[str, Any]]:
        """Get all log entries with a specific correlation ID."""
        events = []

        # Search audit log
        if self.audit_db_path.exists():
            try:
                async with aiosqlite.connect(str(self.audit_db_path)) as db:
                    db.row_factory = aiosqlite.Row
                    cursor = await db.execute(
                        """
                        SELECT * FROM audit_log
                        WHERE action_details LIKE ?
                        ORDER BY timestamp ASC
                        """,
                        (f'%{correlation_id}%',)
                    )
                    rows = await cursor.fetchall()

                    for row in rows:
                        entry = dict(row)
                        entry["source"] = "audit"
                        if entry.get("action_details"):
                            try:
                                entry["action_details"] = json.loads(entry["action_details"])
                            except json.JSONDecodeError:
                                pass
                        events.append(entry)

            except Exception as e:
                logger.warning(f"Failed to search audit log: {e}")

        # Search frontend errors
        if self.frontend_errors_path.exists():
            try:
                with open(self.frontend_errors_path, "r") as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            if entry.get("correlation_id") == correlation_id:
                                entry["source"] = "frontend"
                                events.append(entry)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.warning(f"Failed to search frontend errors: {e}")

        return events

    async def get_failure_counts(
        self,
        hours: int = 1
    ) -> Dict[str, int]:
        """Get failure counts by agent for the past N hours."""
        if not self.audit_db_path.exists():
            return {}

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        counts = defaultdict(int)

        try:
            async with aiosqlite.connect(str(self.audit_db_path)) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    """
                    SELECT agent_name, COUNT(*) as count
                    FROM audit_log
                    WHERE status = 'failure'
                    AND timestamp >= ?
                    GROUP BY agent_name
                    """,
                    (cutoff,)
                )
                rows = await cursor.fetchall()

                for row in rows:
                    counts[row["agent_name"]] = row["count"]

        except Exception as e:
            logger.warning(f"Failed to get failure counts: {e}")

        return dict(counts)

    async def search(
        self,
        query: str,
        source: Optional[str] = None,
        hours: int = 24,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Full-text search across all log sources.

        Args:
            query: Search query
            source: Optional source filter
            hours: Time window
            limit: Maximum results

        Returns:
            Matching log entries
        """
        await self.initialize()

        results = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()
        query_lower = query.lower()

        # Search audit log
        if source is None or source == "audit":
            if self.audit_db_path.exists():
                try:
                    async with aiosqlite.connect(str(self.audit_db_path)) as db:
                        db.row_factory = aiosqlite.Row
                        cursor = await db.execute(
                            """
                            SELECT * FROM audit_log
                            WHERE timestamp >= ?
                            AND (
                                action_details LIKE ?
                                OR error_message LIKE ?
                                OR agent_name LIKE ?
                                OR action_type LIKE ?
                                OR input_summary LIKE ?
                                OR output_summary LIKE ?
                            )
                            ORDER BY timestamp DESC
                            LIMIT ?
                            """,
                            (
                                cutoff_str,
                                f"%{query}%", f"%{query}%", f"%{query}%",
                                f"%{query}%", f"%{query}%", f"%{query}%",
                                limit
                            )
                        )
                        rows = await cursor.fetchall()

                        for row in rows:
                            entry = dict(row)
                            entry["source"] = "audit"
                            results.append(entry)

                except Exception as e:
                    logger.warning(f"Failed to search audit log: {e}")

        # Search retry queue
        if source is None or source == "retry_queue":
            if self.retry_queue_path.exists():
                try:
                    with open(self.retry_queue_path, "r") as f:
                        for line in f:
                            if query_lower in line.lower():
                                try:
                                    entry = json.loads(line.strip())
                                    entry["source"] = "retry_queue"
                                    results.append(entry)

                                    if len(results) >= limit:
                                        break
                                except json.JSONDecodeError:
                                    continue
                except Exception as e:
                    logger.warning(f"Failed to search retry queue: {e}")

        # Search frontend errors
        if source is None or source == "frontend":
            if self.frontend_errors_path.exists():
                try:
                    with open(self.frontend_errors_path, "r") as f:
                        for line in f:
                            if query_lower in line.lower():
                                try:
                                    entry = json.loads(line.strip())
                                    entry["source"] = "frontend"
                                    results.append(entry)

                                    if len(results) >= limit:
                                        break
                                except json.JSONDecodeError:
                                    continue
                except Exception as e:
                    logger.warning(f"Failed to search frontend errors: {e}")

        # Sort by timestamp and limit
        results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return results[:limit]
