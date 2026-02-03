"""
KPI Dashboard - RevOps Metrics Tracking and Visualization
Tracks campaign, pipeline, agent, and conversion KPIs with alerting.
"""

import os
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


PROJECT_ROOT = Path(__file__).parent.parent
HIVE_MIND = PROJECT_ROOT / ".hive-mind"
CONFIG_DIR = PROJECT_ROOT / "config"


class KPICategory(Enum):
    PIPELINE = "pipeline"
    CAMPAIGN = "campaign"
    AGENT = "agent"
    CONVERSION = "conversion"


class KPIStatus(Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    ALERT = "alert"
    UNKNOWN = "unknown"


class TrendDirection(Enum):
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


@dataclass
class KPIMetric:
    name: str
    value: float
    target: float
    threshold_warning: float
    threshold_alert: float
    unit: str = "%"
    trend: TrendDirection = TrendDirection.STABLE
    status: KPIStatus = KPIStatus.UNKNOWN
    category: KPICategory = KPICategory.CAMPAIGN
    last_updated: str = ""
    
    def __post_init__(self):
        self.last_updated = datetime.now().isoformat()
        self._calculate_status()
    
    def _calculate_status(self):
        if self.value >= self.target:
            self.status = KPIStatus.HEALTHY
        elif self.value >= self.threshold_warning:
            self.status = KPIStatus.WARNING
        elif self.value >= self.threshold_alert:
            self.status = KPIStatus.ALERT
        else:
            self.status = KPIStatus.ALERT
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "target": self.target,
            "threshold_warning": self.threshold_warning,
            "threshold_alert": self.threshold_alert,
            "unit": self.unit,
            "trend": self.trend.value,
            "status": self.status.value,
            "category": self.category.value,
            "last_updated": self.last_updated
        }


@dataclass
class DashboardConfig:
    targets: dict = field(default_factory=lambda: {
        "icp_match_rate": {"target": 80, "warning": 70, "alert": 60, "unit": "%", "category": "pipeline"},
        "ae_approval_rate": {"target": 70, "warning": 50, "alert": 40, "unit": "%", "category": "pipeline"},
        "email_open_rate": {"target": 50, "warning": 40, "alert": 30, "unit": "%", "category": "campaign"},
        "reply_rate": {"target": 8, "warning": 5, "alert": 3, "unit": "%", "category": "campaign"},
        "positive_reply_rate": {"target": 60, "warning": 40, "alert": 30, "unit": "%", "category": "conversion"},
        "meeting_book_rate": {"target": 2, "warning": 1, "alert": 0.5, "unit": "%", "category": "conversion"},
        "ghost_recovery_rate": {"target": 15, "warning": 10, "alert": 5, "unit": "%", "category": "conversion"},
        "agent_accuracy": {"target": 90, "warning": 80, "alert": 70, "unit": "%", "category": "agent"}
    })
    refresh_interval_minutes: int = 15
    history_days: int = 30
    
    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "DashboardConfig":
        if config_path and config_path.exists():
            try:
                with open(config_path) as f:
                    data = json.load(f)
                return cls(**data)
            except Exception:
                pass
        return cls()


class KPIDashboard:
    def __init__(self, config: Optional[DashboardConfig] = None):
        self.config = config or DashboardConfig.load(CONFIG_DIR / "kpi_config.json")
        self.metrics: dict[str, KPIMetric] = {}
        self.history: dict[str, list] = {}
        self._load_history()
    
    def _load_history(self):
        history_file = HIVE_MIND / "kpi_history.json"
        if history_file.exists():
            try:
                with open(history_file) as f:
                    self.history = json.load(f)
            except Exception:
                self.history = {}
    
    def _save_history(self):
        HIVE_MIND.mkdir(parents=True, exist_ok=True)
        history_file = HIVE_MIND / "kpi_history.json"
        try:
            with open(history_file, "w") as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")
    
    def fetch_instantly_metrics(self) -> dict:
        """Fetch campaign stats from Instantly API."""
        metrics = {}
        
        campaigns_dir = HIVE_MIND / "campaigns"
        if not campaigns_dir.exists():
            return self._get_default_campaign_metrics()
        
        total_sent = 0
        total_opened = 0
        total_replied = 0
        total_positive = 0
        
        for f in campaigns_dir.glob("*.json"):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                    stats = data.get("stats", {})
                    total_sent += stats.get("sent", 0)
                    total_opened += stats.get("opened", 0)
                    total_replied += stats.get("replied", 0)
                    total_positive += stats.get("positive_replies", 0)
            except Exception:
                pass
        
        if total_sent > 0:
            metrics["email_open_rate"] = (total_opened / total_sent) * 100
            metrics["reply_rate"] = (total_replied / total_sent) * 100
        else:
            metrics["email_open_rate"] = 0
            metrics["reply_rate"] = 0
        
        if total_replied > 0:
            metrics["positive_reply_rate"] = (total_positive / total_replied) * 100
        else:
            metrics["positive_reply_rate"] = 0
        
        return metrics
    
    def _get_default_campaign_metrics(self) -> dict:
        return {
            "email_open_rate": 0,
            "reply_rate": 0,
            "positive_reply_rate": 0
        }
    
    def fetch_ghl_metrics(self) -> dict:
        """Fetch pipeline stats from GoHighLevel."""
        metrics = {}
        
        pipeline_file = HIVE_MIND / "pipeline_stats.json"
        if pipeline_file.exists():
            try:
                with open(pipeline_file) as f:
                    data = json.load(f)
                    metrics["icp_match_rate"] = data.get("icp_match_rate", 0)
                    metrics["meeting_book_rate"] = data.get("meeting_book_rate", 0)
                    metrics["ghost_recovery_rate"] = data.get("ghost_recovery_rate", 0)
            except Exception:
                pass
        
        review_log = HIVE_MIND / "review_log.json"
        if review_log.exists():
            try:
                with open(review_log) as f:
                    data = json.load(f)
                    reviews = data.get("reviews", [])
                    if reviews:
                        approved = sum(1 for r in reviews if r.get("action") == "approved")
                        metrics["ae_approval_rate"] = (approved / len(reviews)) * 100
            except Exception:
                pass
        
        if "icp_match_rate" not in metrics:
            metrics["icp_match_rate"] = 0
        if "ae_approval_rate" not in metrics:
            metrics["ae_approval_rate"] = 0
        if "meeting_book_rate" not in metrics:
            metrics["meeting_book_rate"] = 0
        if "ghost_recovery_rate" not in metrics:
            metrics["ghost_recovery_rate"] = 0
        
        return metrics
    
    def fetch_agent_metrics(self) -> dict:
        """Fetch agent performance metrics from logs."""
        metrics = {}
        
        agent_log = HIVE_MIND / "agent_performance.json"
        if agent_log.exists():
            try:
                with open(agent_log) as f:
                    data = json.load(f)
                    metrics["agent_accuracy"] = data.get("accuracy", 0)
            except Exception:
                pass
        
        if "agent_accuracy" not in metrics:
            execution_dir = PROJECT_ROOT / "execution"
            if execution_dir.exists():
                total_runs = 0
                successful_runs = 0
                for f in execution_dir.glob("*.json"):
                    try:
                        with open(f) as fh:
                            data = json.load(fh)
                            total_runs += 1
                            if data.get("status") == "success":
                                successful_runs += 1
                    except Exception:
                        pass
                if total_runs > 0:
                    metrics["agent_accuracy"] = (successful_runs / total_runs) * 100
                else:
                    metrics["agent_accuracy"] = 0
            else:
                metrics["agent_accuracy"] = 0
        
        return metrics
    
    def calculate_all_kpis(self) -> dict[str, KPIMetric]:
        """Compute all metrics from all data sources."""
        instantly_metrics = self.fetch_instantly_metrics()
        ghl_metrics = self.fetch_ghl_metrics()
        agent_metrics = self.fetch_agent_metrics()
        
        all_raw_metrics = {**instantly_metrics, **ghl_metrics, **agent_metrics}
        
        for metric_name, config in self.config.targets.items():
            value = all_raw_metrics.get(metric_name, 0)
            
            category_map = {
                "pipeline": KPICategory.PIPELINE,
                "campaign": KPICategory.CAMPAIGN,
                "agent": KPICategory.AGENT,
                "conversion": KPICategory.CONVERSION
            }
            category = category_map.get(config.get("category", "campaign"), KPICategory.CAMPAIGN)
            
            trend = self.get_trend(metric_name)
            
            kpi = KPIMetric(
                name=metric_name,
                value=round(value, 2),
                target=config["target"],
                threshold_warning=config["warning"],
                threshold_alert=config["alert"],
                unit=config.get("unit", "%"),
                trend=trend,
                category=category
            )
            
            self.metrics[metric_name] = kpi
            
            if metric_name not in self.history:
                self.history[metric_name] = []
            self.history[metric_name].append({
                "value": value,
                "timestamp": datetime.now().isoformat()
            })
            cutoff = datetime.now() - timedelta(days=self.config.history_days)
            self.history[metric_name] = [
                h for h in self.history[metric_name]
                if datetime.fromisoformat(h["timestamp"]) > cutoff
            ]
        
        self._save_history()
        
        return self.metrics
    
    def get_trend(self, metric: str, days: int = 7) -> TrendDirection:
        """Calculate trend direction over specified days."""
        if metric not in self.history:
            return TrendDirection.STABLE
        
        history = self.history[metric]
        if len(history) < 2:
            return TrendDirection.STABLE
        
        cutoff = datetime.now() - timedelta(days=days)
        recent = [h for h in history if datetime.fromisoformat(h["timestamp"]) > cutoff]
        
        if len(recent) < 2:
            return TrendDirection.STABLE
        
        first_half = recent[:len(recent)//2]
        second_half = recent[len(recent)//2:]
        
        avg_first = sum(h["value"] for h in first_half) / len(first_half)
        avg_second = sum(h["value"] for h in second_half) / len(second_half)
        
        diff = avg_second - avg_first
        threshold = 2.0
        
        if diff > threshold:
            return TrendDirection.UP
        elif diff < -threshold:
            return TrendDirection.DOWN
        else:
            return TrendDirection.STABLE
    
    def check_alerts(self) -> list[dict]:
        """Return list of breached thresholds."""
        alerts = []
        
        for name, kpi in self.metrics.items():
            if kpi.status in [KPIStatus.WARNING, KPIStatus.ALERT]:
                alerts.append({
                    "metric": name,
                    "value": kpi.value,
                    "target": kpi.target,
                    "status": kpi.status.value,
                    "category": kpi.category.value,
                    "message": self._generate_alert_message(kpi)
                })
        
        return alerts
    
    def _generate_alert_message(self, kpi: KPIMetric) -> str:
        if kpi.status == KPIStatus.ALERT:
            return f"CRITICAL: {kpi.name} at {kpi.value}{kpi.unit} (target: {kpi.target}{kpi.unit})"
        elif kpi.status == KPIStatus.WARNING:
            return f"WARNING: {kpi.name} at {kpi.value}{kpi.unit} (target: {kpi.target}{kpi.unit})"
        return ""
    
    def generate_json_report(self) -> Path:
        """Export metrics to .hive-mind/kpi_report.json."""
        HIVE_MIND.mkdir(parents=True, exist_ok=True)
        report_path = HIVE_MIND / "kpi_report.json"
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "metrics": {name: kpi.to_dict() for name, kpi in self.metrics.items()},
            "alerts": self.check_alerts(),
            "summary": {
                "total_metrics": len(self.metrics),
                "healthy": sum(1 for k in self.metrics.values() if k.status == KPIStatus.HEALTHY),
                "warning": sum(1 for k in self.metrics.values() if k.status == KPIStatus.WARNING),
                "alert": sum(1 for k in self.metrics.values() if k.status == KPIStatus.ALERT)
            }
        }
        
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"JSON report generated: {report_path}")
        return report_path
    
    def generate_html_dashboard(self) -> Path:
        """Create dashboard/index.html with KPI visualization."""
        dashboard_dir = PROJECT_ROOT / "dashboard"
        dashboard_dir.mkdir(parents=True, exist_ok=True)
        html_path = dashboard_dir / "kpi_index.html"
        
        status_colors = {
            "healthy": "#22c55e",
            "warning": "#eab308",
            "alert": "#ef4444",
            "unknown": "#6b7280"
        }
        
        trend_arrows = {
            "up": "↑",
            "down": "↓",
            "stable": "→"
        }
        
        metrics_html = ""
        for category in KPICategory:
            category_metrics = [m for m in self.metrics.values() if m.category == category]
            if not category_metrics:
                continue
            
            metrics_html += f'<div class="category"><h2>{category.value.upper()}</h2><div class="cards">'
            
            for kpi in category_metrics:
                color = status_colors.get(kpi.status.value, "#6b7280")
                arrow = trend_arrows.get(kpi.trend.value, "→")
                trend_color = "#22c55e" if kpi.trend == TrendDirection.UP else "#ef4444" if kpi.trend == TrendDirection.DOWN else "#6b7280"
                
                display_name = kpi.name.replace("_", " ").title()
                
                metrics_html += f'''
                <div class="card" style="border-left: 4px solid {color};">
                    <div class="card-header">
                        <span class="card-title">{display_name}</span>
                        <span class="trend" style="color: {trend_color};">{arrow}</span>
                    </div>
                    <div class="card-value" style="color: {color};">{kpi.value}{kpi.unit}</div>
                    <div class="card-target">Target: {kpi.target}{kpi.unit}</div>
                    <div class="card-status status-{kpi.status.value}">{kpi.status.value.upper()}</div>
                </div>
                '''
            
            metrics_html += '</div></div>'
        
        alerts = self.check_alerts()
        alerts_html = ""
        if alerts:
            alerts_html = '<div class="alerts"><h2>Active Alerts</h2><ul>'
            for alert in alerts:
                alert_class = "alert-critical" if alert["status"] == "alert" else "alert-warning"
                alerts_html += f'<li class="{alert_class}">{alert["message"]}</li>'
            alerts_html += '</ul></div>'
        
        summary = {
            "healthy": sum(1 for k in self.metrics.values() if k.status == KPIStatus.HEALTHY),
            "warning": sum(1 for k in self.metrics.values() if k.status == KPIStatus.WARNING),
            "alert": sum(1 for k in self.metrics.values() if k.status == KPIStatus.ALERT)
        }
        
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RevOps KPI Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            padding: 20px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #334155;
        }}
        h1 {{ color: #f8fafc; font-size: 24px; }}
        .timestamp {{ color: #94a3b8; font-size: 14px; }}
        .summary {{
            display: flex;
            gap: 20px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: #1e293b;
            padding: 15px 25px;
            border-radius: 8px;
            text-align: center;
        }}
        .summary-card .count {{ font-size: 32px; font-weight: bold; }}
        .summary-card .label {{ color: #94a3b8; font-size: 12px; text-transform: uppercase; }}
        .summary-card.healthy .count {{ color: #22c55e; }}
        .summary-card.warning .count {{ color: #eab308; }}
        .summary-card.alert .count {{ color: #ef4444; }}
        .alerts {{
            background: #1e293b;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }}
        .alerts h2 {{ margin-bottom: 15px; font-size: 18px; }}
        .alerts ul {{ list-style: none; }}
        .alerts li {{ 
            padding: 10px 15px;
            margin-bottom: 8px;
            border-radius: 4px;
        }}
        .alert-critical {{ background: rgba(239, 68, 68, 0.2); border-left: 3px solid #ef4444; }}
        .alert-warning {{ background: rgba(234, 179, 8, 0.2); border-left: 3px solid #eab308; }}
        .category {{ margin-bottom: 30px; }}
        .category h2 {{ 
            font-size: 16px; 
            color: #94a3b8; 
            margin-bottom: 15px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 20px;
        }}
        .card {{
            background: #1e293b;
            padding: 20px;
            border-radius: 8px;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }}
        .card-title {{ font-size: 14px; color: #94a3b8; }}
        .trend {{ font-size: 18px; }}
        .card-value {{ font-size: 36px; font-weight: bold; margin-bottom: 5px; }}
        .card-target {{ color: #64748b; font-size: 12px; margin-bottom: 10px; }}
        .card-status {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .status-healthy {{ background: rgba(34, 197, 94, 0.2); color: #22c55e; }}
        .status-warning {{ background: rgba(234, 179, 8, 0.2); color: #eab308; }}
        .status-alert {{ background: rgba(239, 68, 68, 0.2); color: #ef4444; }}
        .status-unknown {{ background: rgba(107, 114, 128, 0.2); color: #6b7280; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>RevOps KPI Dashboard</h1>
        <span class="timestamp">Last updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
    </div>
    
    <div class="summary">
        <div class="summary-card healthy">
            <div class="count">{summary["healthy"]}</div>
            <div class="label">Healthy</div>
        </div>
        <div class="summary-card warning">
            <div class="count">{summary["warning"]}</div>
            <div class="label">Warning</div>
        </div>
        <div class="summary-card alert">
            <div class="count">{summary["alert"]}</div>
            <div class="label">Alert</div>
        </div>
    </div>
    
    {alerts_html}
    
    {metrics_html}
</body>
</html>
'''
        
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        print(f"HTML dashboard generated: {html_path}")
        return html_path


def main():
    parser = argparse.ArgumentParser(description="KPI Dashboard - RevOps Metrics Tracking")
    parser.add_argument("--json", action="store_true", help="Generate JSON report")
    parser.add_argument("--html", action="store_true", help="Generate HTML dashboard")
    parser.add_argument("--alerts", action="store_true", help="Show active alerts only")
    parser.add_argument("--all", action="store_true", help="Generate all outputs")
    
    args = parser.parse_args()
    
    dashboard = KPIDashboard()
    dashboard.calculate_all_kpis()
    
    if args.all or (not args.json and not args.html and not args.alerts):
        dashboard.generate_json_report()
        dashboard.generate_html_dashboard()
        alerts = dashboard.check_alerts()
        if alerts:
            print(f"\n{len(alerts)} Active Alerts:")
            for alert in alerts:
                print(f"  - {alert['message']}")
        else:
            print("\nNo active alerts.")
        return
    
    if args.json:
        dashboard.generate_json_report()
    
    if args.html:
        dashboard.generate_html_dashboard()
    
    if args.alerts:
        alerts = dashboard.check_alerts()
        if alerts:
            print(f"{len(alerts)} Active Alerts:")
            for alert in alerts:
                print(f"  [{alert['status'].upper()}] {alert['message']}")
        else:
            print("No active alerts.")


if __name__ == "__main__":
    main()
