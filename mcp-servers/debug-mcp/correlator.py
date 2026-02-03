#!/usr/bin/env python3
"""
Error Correlator - Frontend/Backend Error Matching
===================================================

Correlates frontend browser errors with backend service failures using:
- Correlation IDs from X-Correlation-ID headers
- Timestamp proximity matching
- Request path matching
- User session tracking

This enables stitching together the full picture of what went wrong
across the entire stack.
"""

import json
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import logging

try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False

logger = logging.getLogger("debug-mcp.correlator")


@dataclass
class FrontendError:
    """Represents a frontend/browser error."""
    timestamp: str
    message: str
    stack: Optional[str] = None
    url: Optional[str] = None
    correlation_id: Optional[str] = None
    user_agent: Optional[str] = None
    console_type: str = "error"  # error, warn, exception
    source: str = "frontend"


@dataclass
class BackendError:
    """Represents a backend error from audit log."""
    id: int
    timestamp: str
    agent_name: str
    action_type: str
    error_message: Optional[str]
    status: str
    risk_level: str
    correlation_id: Optional[str] = None
    duration_ms: Optional[float] = None
    source: str = "backend"


@dataclass
class CorrelatedError:
    """A correlated error combining frontend and backend context."""
    correlation_id: Optional[str]
    timestamp: str
    frontend_errors: List[Dict[str, Any]]
    backend_error: Optional[Dict[str, Any]]
    match_type: str  # "correlation_id", "timestamp", "path"
    confidence: float  # 0.0 to 1.0
    timeline: List[Dict[str, Any]]


class ErrorCorrelator:
    """
    Correlates frontend and backend errors to provide unified debugging context.

    Matching strategies:
    1. Correlation ID - Exact match via X-Correlation-ID header
    2. Timestamp proximity - Errors within N seconds of each other
    3. Request path - Same API endpoint in frontend request and backend action
    """

    def __init__(
        self,
        audit_db_path: Path,
        frontend_errors_path: Path,
        correlation_window_seconds: int = 60
    ):
        self.audit_db_path = audit_db_path
        self.frontend_errors_path = frontend_errors_path
        self.correlation_window_seconds = correlation_window_seconds
        self._initialized = False

        # In-memory cache for recent frontend errors
        self._frontend_cache: List[FrontendError] = []
        self._cache_max_age_hours = 6

    async def initialize(self):
        """Initialize the correlator."""
        if self._initialized:
            return

        # Ensure paths exist
        self.frontend_errors_path.parent.mkdir(parents=True, exist_ok=True)

        # Load recent frontend errors into cache
        await self._load_frontend_cache()

        self._initialized = True

    async def _load_frontend_cache(self):
        """Load recent frontend errors from JSONL file."""
        self._frontend_cache = []

        if not self.frontend_errors_path.exists():
            return

        cutoff = datetime.now(timezone.utc) - timedelta(hours=self._cache_max_age_hours)

        try:
            with open(self.frontend_errors_path, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        timestamp = data.get("timestamp", "")

                        # Parse timestamp and filter old entries
                        try:
                            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            if ts < cutoff:
                                continue
                        except (ValueError, TypeError):
                            pass

                        self._frontend_cache.append(FrontendError(
                            timestamp=timestamp,
                            message=data.get("message", ""),
                            stack=data.get("stack"),
                            url=data.get("url"),
                            correlation_id=data.get("correlation_id"),
                            user_agent=data.get("user_agent"),
                            console_type=data.get("type", "error")
                        ))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Failed to load frontend errors: {e}")

    async def log_frontend_error(self, error: Dict[str, Any]) -> None:
        """
        Log a frontend error to the JSONL file.

        This should be called from the dashboard's error reporting endpoint.
        """
        error_entry = FrontendError(
            timestamp=error.get("timestamp", datetime.now(timezone.utc).isoformat()),
            message=error.get("message", ""),
            stack=error.get("stack"),
            url=error.get("url"),
            correlation_id=error.get("correlation_id"),
            user_agent=error.get("user_agent"),
            console_type=error.get("type", "error")
        )

        # Add to cache
        self._frontend_cache.append(error_entry)

        # Persist to file
        try:
            with open(self.frontend_errors_path, "a") as f:
                f.write(json.dumps(asdict(error_entry)) + "\n")
        except Exception as e:
            logger.error(f"Failed to persist frontend error: {e}")

    async def get_by_correlation_id(
        self,
        correlation_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get all errors matching a specific correlation ID.

        Args:
            correlation_id: The X-Correlation-ID value

        Returns:
            Correlated error with frontend and backend context
        """
        await self.initialize()

        # Find frontend errors with this correlation ID
        frontend_errors = [
            asdict(e) for e in self._frontend_cache
            if e.correlation_id == correlation_id
        ]

        # Find backend errors with this correlation ID
        backend_error = None

        if self.audit_db_path.exists():
            try:
                async with aiosqlite.connect(str(self.audit_db_path)) as db:
                    db.row_factory = aiosqlite.Row
                    cursor = await db.execute(
                        """
                        SELECT * FROM audit_log
                        WHERE action_details LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT 1
                        """,
                        (f'%"correlation_id": "{correlation_id}"%',)
                    )
                    row = await cursor.fetchone()

                    if row:
                        backend_error = dict(row)
                        if backend_error.get("action_details"):
                            backend_error["action_details"] = json.loads(
                                backend_error["action_details"]
                            )
            except Exception as e:
                logger.warning(f"Failed to query audit log: {e}")

        if not frontend_errors and not backend_error:
            return None

        # Build timeline
        timeline = []
        for fe in frontend_errors:
            timeline.append({
                "timestamp": fe["timestamp"],
                "source": "frontend",
                "type": fe["console_type"],
                "message": fe["message"][:200]
            })

        if backend_error:
            timeline.append({
                "timestamp": backend_error.get("timestamp"),
                "source": "backend",
                "type": backend_error.get("action_type"),
                "message": backend_error.get("error_message", "")[:200]
            })

        # Sort by timestamp
        timeline.sort(key=lambda x: x.get("timestamp", ""))

        return {
            "correlation_id": correlation_id,
            "match_type": "correlation_id",
            "confidence": 1.0,
            "frontend_errors": frontend_errors,
            "backend_error": backend_error,
            "timeline": timeline
        }

    async def get_recent_correlated(
        self,
        time_window_seconds: int = 60,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get recent errors correlated by timestamp proximity.

        Matches frontend errors to backend failures that occurred within
        the specified time window.

        Args:
            time_window_seconds: How close in time errors must be to correlate
            limit: Maximum number of correlated errors to return

        Returns:
            List of correlated error objects
        """
        await self.initialize()

        # Get recent backend failures
        backend_failures = []

        if self.audit_db_path.exists():
            try:
                cutoff = (
                    datetime.now(timezone.utc) - timedelta(hours=self._cache_max_age_hours)
                ).isoformat()

                async with aiosqlite.connect(str(self.audit_db_path)) as db:
                    db.row_factory = aiosqlite.Row
                    cursor = await db.execute(
                        """
                        SELECT * FROM audit_log
                        WHERE status = 'failure'
                        AND timestamp >= ?
                        ORDER BY timestamp DESC
                        LIMIT 100
                        """,
                        (cutoff,)
                    )
                    rows = await cursor.fetchall()

                    for row in rows:
                        entry = dict(row)
                        if entry.get("action_details"):
                            try:
                                entry["action_details"] = json.loads(entry["action_details"])
                            except json.JSONDecodeError:
                                pass
                        backend_failures.append(entry)
            except Exception as e:
                logger.warning(f"Failed to query audit log: {e}")

        # Correlate with frontend errors
        correlated = []
        used_frontend_ids = set()

        for backend in backend_failures:
            backend_ts = backend.get("timestamp", "")

            try:
                backend_dt = datetime.fromisoformat(backend_ts.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            # Find frontend errors within the time window
            matching_frontend = []

            for i, fe in enumerate(self._frontend_cache):
                if i in used_frontend_ids:
                    continue

                try:
                    fe_dt = datetime.fromisoformat(fe.timestamp.replace("Z", "+00:00"))
                    time_diff = abs((backend_dt - fe_dt).total_seconds())

                    if time_diff <= time_window_seconds:
                        matching_frontend.append(asdict(fe))
                        used_frontend_ids.add(i)
                except (ValueError, TypeError):
                    continue

            if matching_frontend:
                # Calculate confidence based on time proximity
                avg_time_diff = sum(
                    abs((backend_dt - datetime.fromisoformat(
                        fe["timestamp"].replace("Z", "+00:00")
                    )).total_seconds())
                    for fe in matching_frontend
                ) / len(matching_frontend)

                confidence = max(0.5, 1.0 - (avg_time_diff / time_window_seconds))

                # Build timeline
                timeline = []
                for fe in matching_frontend:
                    timeline.append({
                        "timestamp": fe["timestamp"],
                        "source": "frontend",
                        "type": fe.get("console_type", "error"),
                        "message": fe.get("message", "")[:200]
                    })

                timeline.append({
                    "timestamp": backend_ts,
                    "source": "backend",
                    "type": backend.get("action_type"),
                    "message": backend.get("error_message", "")[:200] if backend.get("error_message") else ""
                })

                timeline.sort(key=lambda x: x.get("timestamp", ""))

                correlated.append({
                    "correlation_id": backend.get("action_details", {}).get("correlation_id"),
                    "match_type": "timestamp",
                    "confidence": round(confidence, 2),
                    "frontend_errors": matching_frontend,
                    "backend_error": backend,
                    "timeline": timeline
                })

                if len(correlated) >= limit:
                    break

        return correlated

    async def get_unmatched_frontend_errors(
        self,
        hours: int = 6,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get frontend errors that couldn't be correlated to any backend failure.

        These might indicate client-side issues, network problems, or
        errors that didn't propagate to the backend.
        """
        await self.initialize()

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        unmatched = []

        for fe in self._frontend_cache:
            try:
                fe_dt = datetime.fromisoformat(fe.timestamp.replace("Z", "+00:00"))
                if fe_dt < cutoff:
                    continue
            except (ValueError, TypeError):
                continue

            # Check if there's a correlation ID that matches backend
            if fe.correlation_id:
                correlated = await self.get_by_correlation_id(fe.correlation_id)
                if correlated and correlated.get("backend_error"):
                    continue

            unmatched.append(asdict(fe))

            if len(unmatched) >= limit:
                break

        return unmatched

    async def get_error_chain(
        self,
        start_error_id: int,
        max_depth: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get the chain of errors that followed from an initial error.

        Useful for understanding cascading failures.

        Args:
            start_error_id: The audit log ID of the initial error
            max_depth: Maximum chain length to follow

        Returns:
            Chain of related errors
        """
        await self.initialize()

        if not self.audit_db_path.exists():
            return []

        chain = []

        try:
            async with aiosqlite.connect(str(self.audit_db_path)) as db:
                db.row_factory = aiosqlite.Row

                # Get the starting error
                cursor = await db.execute(
                    "SELECT * FROM audit_log WHERE id = ?",
                    (start_error_id,)
                )
                start_row = await cursor.fetchone()

                if not start_row:
                    return []

                start_entry = dict(start_row)
                chain.append(start_entry)

                # Get subsequent errors from the same agent within 5 minutes
                start_ts = start_entry.get("timestamp", "")
                agent = start_entry.get("agent_name", "")

                cursor = await db.execute(
                    """
                    SELECT * FROM audit_log
                    WHERE agent_name = ?
                    AND timestamp > ?
                    AND timestamp <= datetime(?, '+5 minutes')
                    AND status = 'failure'
                    ORDER BY timestamp ASC
                    LIMIT ?
                    """,
                    (agent, start_ts, start_ts, max_depth - 1)
                )

                rows = await cursor.fetchall()

                for row in rows:
                    entry = dict(row)
                    if entry.get("action_details"):
                        try:
                            entry["action_details"] = json.loads(entry["action_details"])
                        except json.JSONDecodeError:
                            pass
                    chain.append(entry)

        except Exception as e:
            logger.warning(f"Failed to get error chain: {e}")

        return chain
