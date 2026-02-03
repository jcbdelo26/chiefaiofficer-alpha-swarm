#!/usr/bin/env python3
"""
Streamlit Health Dashboard for CAIO RevOps Swarm.

Day 19: Real-time monitoring dashboard with:
- Agent health status
- Circuit breaker states
- Queue depths
- Rate limits
- Latency percentiles (p50/p95/p99)
- ReasoningBank stats
- Recent alerts

Usage:
    streamlit run dashboard/health_dashboard.py
"""

import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
import time

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import streamlit as st
    import pandas as pd
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    print("Streamlit not installed. Run: pip install streamlit")

from core.unified_health_monitor import get_health_monitor, HealthStatus


def get_status_color(status: str) -> str:
    """Get color for status badge."""
    colors = {
        "healthy": "#28a745",  # Green
        "degraded": "#ffc107",  # Yellow
        "unhealthy": "#dc3545",  # Red
        "ok": "#28a745",
        "warning": "#ffc107",
        "critical": "#dc3545",
        "missing": "#6c757d",  # Gray
        "error": "#dc3545",
    }
    return colors.get(status.lower(), "#6c757d")


def status_badge(status: str) -> str:
    """Create HTML status badge."""
    color = get_status_color(status)
    return f'<span style="background-color: {color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{status.upper()}</span>'


def run_dashboard():
    """Main dashboard function."""
    if not STREAMLIT_AVAILABLE:
        print("Streamlit is required for the dashboard.")
        return

    # Page config
    st.set_page_config(
        page_title="CAIO Health Monitor",
        page_icon="🏥",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Custom CSS
    st.markdown("""
    <style>
        .metric-card {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            padding: 20px;
            border-radius: 10px;
            color: white;
            margin-bottom: 10px;
        }
        .metric-value {
            font-size: 36px;
            font-weight: bold;
        }
        .metric-label {
            font-size: 14px;
            opacity: 0.8;
        }
        .agent-card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #28a745;
            margin-bottom: 10px;
        }
        .agent-card.degraded {
            border-left-color: #ffc107;
        }
        .agent-card.unhealthy {
            border-left-color: #dc3545;
        }
        .queue-bar {
            height: 20px;
            border-radius: 4px;
            background: #e9ecef;
            margin: 5px 0;
        }
        .queue-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }
    </style>
    """, unsafe_allow_html=True)

    # Header
    st.title("🏥 CAIO RevOps Swarm Health Monitor")
    st.markdown("Real-time health monitoring for the Chief AI Officer automation system")

    # Get health monitor
    monitor = get_health_monitor()
    health_status = monitor.get_health_status()

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Settings")
        refresh_rate = st.slider("Refresh Rate (seconds)", 5, 60, 30)
        
        st.markdown("---")
        st.header("📊 Quick Stats")
        st.metric("Health Score", f"{health_status.get('health_score', 0)}/100")
        st.metric("System Status", health_status.get("status", "unknown").upper())
        st.metric("Stale Agents", len(health_status.get("stale_agents", [])))
        
        st.markdown("---")
        if st.button("🔄 Refresh Now"):
            st.rerun()
        
        st.markdown("---")
        st.caption(f"Last updated: {health_status.get('timestamp', 'N/A')[:19]}")

    # Main content - Row 1: Overview
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        score = health_status.get("health_score", 0)
        color = "#28a745" if score >= 80 else "#ffc107" if score >= 60 else "#dc3545"
        st.markdown(f"""
        <div class="metric-card" style="background: {color};">
            <div class="metric-value">{score}</div>
            <div class="metric-label">Health Score</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        agents = health_status.get("agents", {})
        healthy = sum(1 for a in agents.values() if a.get("status") == "healthy")
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{healthy}/{len(agents)}</div>
            <div class="metric-label">Healthy Agents</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        email_limits = health_status.get("email_limits", {})
        daily = email_limits.get("daily", {})
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{daily.get('sent', 0)}/{daily.get('limit', 500)}</div>
            <div class="metric-label">Daily Emails</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        alerts = health_status.get("alerts", [])
        critical = sum(1 for a in alerts if a.get("severity") == "critical")
        st.markdown(f"""
        <div class="metric-card" style="{'background: #dc3545;' if critical > 0 else ''}">
            <div class="metric-value">{len(alerts)}</div>
            <div class="metric-label">Active Alerts ({critical} Critical)</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Row 2: Tabs for detailed views
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🤖 Agents", "📊 Queues", "⏱️ Latency", "🔒 Rate Limits", "⚠️ Alerts"
    ])

    with tab1:
        st.subheader("Agent Health Status")
        
        agents = health_status.get("agents", {})
        
        # Create columns for agents
        cols = st.columns(3)
        for idx, (name, data) in enumerate(agents.items()):
            with cols[idx % 3]:
                status = data.get("status", "unknown")
                status_class = status if status in ["degraded", "unhealthy"] else ""
                
                st.markdown(f"""
                <div class="agent-card {status_class}">
                    <strong>{name}</strong> {status_badge(status)}
                    <br/><small>
                        Requests: {data.get('total_requests', 0)} | 
                        Errors: {data.get('error_rate', 0):.1f}% |
                        Latency: {data.get('avg_latency_ms', 0):.0f}ms
                    </small>
                </div>
                """, unsafe_allow_html=True)
        
        # Heartbeats
        st.subheader("Heartbeats")
        heartbeats = health_status.get("heartbeats", {})
        if heartbeats:
            hb_data = []
            for agent, hb in heartbeats.items():
                hb_data.append({
                    "Agent": agent,
                    "Last Heartbeat": hb.get("last_heartbeat", "N/A")[:19],
                    "Age (s)": hb.get("age_seconds", 0),
                    "Status": "🔴 Stale" if hb.get("is_stale") else "🟢 Active"
                })
            st.dataframe(pd.DataFrame(hb_data), use_container_width=True)
        else:
            st.info("No heartbeats recorded yet")

    with tab2:
        st.subheader("Queue Depths")
        
        queue_depths = health_status.get("queue_depths", {})
        
        for name, queue in queue_depths.items():
            usage = queue.get("usage_percent", 0)
            status = queue.get("status", "healthy")
            color = get_status_color(status)
            
            st.markdown(f"**{queue.get('name', name)}** - {status_badge(status)}")
            st.progress(min(usage / 100, 1.0))
            st.caption(f"{queue.get('current_depth', 0)}/{queue.get('max_depth', 1000)} ({usage:.1f}%) | Processed: {queue.get('total_processed', 0)} | Dropped: {queue.get('total_dropped', 0)}")
            st.markdown("---")
        
        # ReasoningBank stats
        st.subheader("ReasoningBank")
        rb_stats = health_status.get("reasoning_bank", {})
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Entries", rb_stats.get("entries", 0))
        with col2:
            st.metric("Size", f"{rb_stats.get('size_mb', 0):.2f} MB")
        with col3:
            st.metric("Status", rb_stats.get("status", "N/A").upper())

    with tab3:
        st.subheader("Latency Percentiles (5-min window)")
        
        latency_stats = health_status.get("latency_stats", {})
        
        if latency_stats:
            lat_data = []
            for component, stats in latency_stats.items():
                lat_data.append({
                    "Component": component,
                    "p50 (ms)": stats.get("p50_ms", 0),
                    "p95 (ms)": stats.get("p95_ms", 0),
                    "p99 (ms)": stats.get("p99_ms", 0),
                    "Samples": stats.get("samples", 0)
                })
            st.dataframe(pd.DataFrame(lat_data), use_container_width=True)
        else:
            st.info("No latency data recorded yet")

    with tab4:
        st.subheader("Rate Limit Health")
        
        rate_limits = health_status.get("rate_limits", {})
        
        for name, limit in rate_limits.items():
            usage = limit.get("usage_percent", 0)
            color = "#28a745" if usage < 70 else "#ffc107" if usage < 90 else "#dc3545"
            
            st.markdown(f"**{limit.get('name', name)}** ({limit.get('period', 'N/A')})")
            st.progress(min(usage / 100, 1.0))
            st.caption(f"{limit.get('current', 0)}/{limit.get('limit', 100)} ({usage:.1f}%)")
            st.markdown("---")
        
        # Email limits
        st.subheader("Email Limits")
        email_limits = health_status.get("email_limits", {})
        
        col1, col2, col3 = st.columns(3)
        with col1:
            hourly = email_limits.get("hourly", {})
            st.metric("Hourly", f"{hourly.get('sent', 0)}/{hourly.get('limit', 50)}")
        with col2:
            daily = email_limits.get("daily", {})
            st.metric("Daily", f"{daily.get('sent', 0)}/{daily.get('limit', 500)}")
        with col3:
            monthly = email_limits.get("monthly", {})
            st.metric("Monthly", f"{monthly.get('sent', 0)}/{monthly.get('limit', 10000)}")

    with tab5:
        st.subheader("Recent Alerts")
        
        alerts = health_status.get("alerts", [])
        
        if alerts:
            for alert in reversed(alerts[-10:]):
                severity = alert.get("severity", "info")
                color = get_status_color(severity)
                
                st.markdown(f"""
                <div style="background: {color}22; border-left: 4px solid {color}; padding: 10px; margin: 5px 0; border-radius: 4px;">
                    <strong>[{severity.upper()}]</strong> {alert.get('message', '')}
                    <br/><small>{alert.get('timestamp', '')[:19]} | Component: {alert.get('component', 'N/A')}</small>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("No active alerts! 🎉")
        
        # Recent actions
        st.subheader("Recent Actions")
        actions = health_status.get("recent_actions", [])
        
        if actions:
            action_data = []
            for action in actions[:10]:
                action_data.append({
                    "Time": action.get("timestamp", "")[:19],
                    "Agent": action.get("agent", ""),
                    "Action": action.get("action", ""),
                    "Status": action.get("status", "")
                })
            st.dataframe(pd.DataFrame(action_data), use_container_width=True)
        else:
            st.info("No recent actions recorded")

    # Integrations and MCP servers collapsible
    with st.expander("📡 Integrations & MCP Servers"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Integrations")
            integrations = health_status.get("integrations", {})
            for name, data in integrations.items():
                status = data.get("status", "unknown")
                st.markdown(f"- **{name}**: {status_badge(status)}", unsafe_allow_html=True)
        
        with col2:
            st.subheader("MCP Servers")
            mcp_servers = health_status.get("mcp_servers", {})
            for name, data in mcp_servers.items():
                status = data.get("status", "unknown")
                st.markdown(f"- **{name}**: {status_badge(status)}", unsafe_allow_html=True)

    # Auto-refresh
    time.sleep(refresh_rate)
    st.rerun()


if __name__ == "__main__":
    run_dashboard()
