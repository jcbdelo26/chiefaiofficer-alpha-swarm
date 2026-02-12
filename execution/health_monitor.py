#!/usr/bin/env python3
"""
Health Monitor
==============
Continuous health monitoring for API connections with alerting.

Features:
- Automated connection testing every 6 hours
- Slack alerts for critical failures
- Historical health tracking in Supabase
- LinkedIn cookie expiration warnings

Usage:
    python execution/health_monitor.py --daemon  # Run as background service
    python execution/health_monitor.py --once    # Run single check
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
import time
import schedule

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Import connection tester
from execution.test_connections import ConnectionTester


class HealthMonitor:
    """Monitor API health and send alerts."""
    
    CRITICAL_SERVICES = ["Supabase", "GoHighLevel", "Instantly", "LinkedIn"]
    LINKEDIN_COOKIE_LIFETIME_DAYS = 30
    WARNING_THRESHOLD_DAYS = 5
    
    def __init__(self):
        self.results_dir = Path(__file__).parent.parent / ".hive-mind"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.health_log = self.results_dir / "health_log.jsonl"
        
    def run_health_check(self) -> Dict[str, Any]:
        """Run comprehensive health check."""
        print(f"\n[{datetime.now().isoformat()}] Running health check...")
        
        tester = ConnectionTester()
        results = tester.run_all_tests()
        
        # Check for critical failures
        critical_failures = self._check_critical_failures(results)
        
        # Check LinkedIn cookie expiration
        cookie_warning = self._check_linkedin_cookie_expiration()
        
        # Check scraper readiness (new Layer 3)
        scraper_readiness = self._check_scraper_readiness()
        
        # Log results
        self._log_health_check(results, critical_failures, cookie_warning)
        
        # Send alerts if needed
        if critical_failures:
            self._send_alerts(critical_failures)
        
        if cookie_warning:
            self._send_cookie_warning(cookie_warning)
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "results": results,
            "critical_failures": critical_failures,
            "cookie_warning": cookie_warning,
            "scraper_readiness": scraper_readiness
        }
    
    def _check_scraper_readiness(self) -> Dict[str, Any]:
        """Check if the LinkedIn scraper is ready to operate.
        
        Validates:
        1. LINKEDIN_COOKIE env var exists and is non-empty
        2. Cookie passes the /voyager/api/me health check (if network available)
        3. Reports scraper status for /api/health/ready endpoint
        """
        import requests
        
        cookie = os.getenv("LINKEDIN_COOKIE", "")
        
        if not cookie:
            return {
                "ready": False,
                "reason": "LINKEDIN_COOKIE not configured",
                "recommendation": "Add li_at cookie to .env or use Proxycurl (PROXYCURL_API_KEY)",
                "fallback_available": True  # test data will be used
            }
        
        if len(cookie) < 150:
            return {
                "ready": False,
                "reason": f"LINKEDIN_COOKIE too short ({len(cookie)} chars, expected 150-400)",
                "recommendation": "Cookie may be truncated. Recopy full li_at from DevTools.",
                "fallback_available": True
            }
        
        # Quick session validation (with tight timeout)
        try:
            headers = {
                "Cookie": f"li_at={cookie}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "x-restli-protocol-version": "2.0.0",
            }
            response = requests.get(
                "https://www.linkedin.com/voyager/api/me",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return {"ready": True, "session_status": "valid", "fallback_available": True}
            elif response.status_code == 401:
                return {
                    "ready": False,
                    "reason": "LinkedIn session EXPIRED (401)",
                    "recommendation": "Rotate li_at cookie and run: python execution/health_monitor.py --update-linkedin-rotation",
                    "fallback_available": True
                }
            elif response.status_code == 403:
                return {
                    "ready": False,
                    "reason": "LinkedIn session BLOCKED (403)",
                    "recommendation": "Account may be rate-limited. Wait 24h or use Proxycurl.",
                    "fallback_available": True
                }
            else:
                return {
                    "ready": False,
                    "reason": f"Unexpected status {response.status_code}",
                    "fallback_available": True
                }
        except requests.exceptions.Timeout:
            return {
                "ready": False,
                "reason": "LinkedIn API unreachable (timeout)",
                "fallback_available": True
            }
        except Exception as e:
            return {
                "ready": False,
                "reason": f"Session check error: {str(e)[:100]}",
                "fallback_available": True
            }
    
    def _check_critical_failures(self, results: Dict[str, Any]) -> List[str]:
        """Check for failures in critical services."""
        failures = []
        
        for service in self.CRITICAL_SERVICES:
            if service in results:
                if not results[service].get("success", False):
                    failures.append({
                        "service": service,
                        "message": results[service].get("message", "Unknown error"),
                        "timestamp": results[service].get("tested_at")
                    })
        
        return failures
    
    def _check_linkedin_cookie_expiration(self) -> Dict[str, Any]:
        """Check if LinkedIn cookie is approaching expiration."""
        # Read last rotation date from log
        last_rotation = self._get_last_linkedin_rotation()
        
        if not last_rotation:
            return {
                "warning": True,
                "message": "LinkedIn cookie rotation date unknown - please update manually",
                "days_remaining": "unknown"
            }
        
        days_since_rotation = (datetime.now() - last_rotation).days
        days_remaining = self.LINKEDIN_COOKIE_LIFETIME_DAYS - days_since_rotation
        
        if days_remaining <= self.WARNING_THRESHOLD_DAYS:
            return {
                "warning": True,
                "message": f"LinkedIn cookie expires in {days_remaining} days!",
                "days_remaining": days_remaining,
                "last_rotation": last_rotation.isoformat()
            }
        
        return None
    
    def _get_last_linkedin_rotation(self) -> datetime:
        """Get last LinkedIn cookie rotation date."""
        rotation_log = self.results_dir / "linkedin_rotation.json"
        
        if not rotation_log.exists():
            return None
        
        try:
            with open(rotation_log, 'r') as f:
                data = json.load(f)
                return datetime.fromisoformat(data.get("last_rotation"))
        except:
            return None
    
    def update_linkedin_rotation(self):
        """Update LinkedIn cookie rotation timestamp."""
        rotation_log = self.results_dir / "linkedin_rotation.json"
        
        with open(rotation_log, 'w') as f:
            json.dump({
                "last_rotation": datetime.now().isoformat(),
                "updated_by": "manual"
            }, f, indent=2)
        
        print(f"✅ LinkedIn rotation timestamp updated: {datetime.now().isoformat()}")
    
    def _log_health_check(self, results: Dict[str, Any], failures: List[str], cookie_warning: Dict):
        """Log health check results to JSONL file."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "results": results,
            "critical_failures": failures,
            "cookie_warning": cookie_warning,
            "overall_health": "healthy" if not failures else "degraded"
        }
        
        with open(self.health_log, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def _send_alerts(self, failures: List[Dict[str, Any]]):
        """Send alerts for critical failures."""
        slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        
        if not slack_webhook or "XXX" in slack_webhook:
            print("⚠️  Slack webhook not configured - skipping alerts")
            self._print_console_alert(failures)
            return
        
        try:
            import requests
            
            message = self._format_slack_message(failures)
            
            response = requests.post(
                slack_webhook,
                json={"text": message},
                timeout=5
            )
            
            if response.status_code == 200:
                print("✅ Alert sent to Slack")
            else:
                print(f"⚠️  Failed to send Slack alert: {response.status_code}")
                self._print_console_alert(failures)
                
        except Exception as e:
            print(f"⚠️  Error sending alert: {e}")
            self._print_console_alert(failures)
    
    def _format_slack_message(self, failures: List[Dict[str, Any]]) -> str:
        """Format alert message for Slack."""
        message = "🚨 *Alpha Swarm Health Alert*\n\n"
        message += f"*Critical Service Failures Detected*\n"
        message += f"Timestamp: {datetime.now().isoformat()}\n\n"
        
        for failure in failures:
            message += f"❌ *{failure['service']}*\n"
            message += f"   Error: {failure['message']}\n"
            message += f"   Time: {failure['timestamp']}\n\n"
        
        message += "\n🔧 *Action Required:*\n"
        message += "1. Check `.env` file for valid credentials\n"
        message += "2. Run `python execution/test_connections.py` for details\n"
        message += "3. Review diagnostic report in `.hive-mind/api_diagnostic_report.md`\n"
        
        return message
    
    def _print_console_alert(self, failures: List[Dict[str, Any]]):
        """Print alert to console when Slack is unavailable."""
        print("\n" + "="*60)
        print("🚨 CRITICAL SERVICE FAILURES DETECTED")
        print("="*60)
        
        for failure in failures:
            print(f"\n❌ {failure['service']}")
            print(f"   Error: {failure['message']}")
            print(f"   Time: {failure['timestamp']}")
        
        print("\n" + "="*60)
    
    def _send_cookie_warning(self, warning: Dict[str, Any]):
        """Send LinkedIn cookie expiration warning."""
        slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        
        message = f"⚠️  *LinkedIn Cookie Expiration Warning*\n\n"
        message += f"{warning['message']}\n\n"
        message += "🔧 *Action Required:*\n"
        message += "1. Log into LinkedIn in incognito mode\n"
        message += "2. Extract `li_at` cookie from DevTools\n"
        message += "3. Update `LINKEDIN_COOKIE` in `.env`\n"
        message += "4. Run `python execution/health_monitor.py --update-linkedin-rotation`\n"
        
        if slack_webhook and "XXX" not in slack_webhook:
            try:
                import requests
                requests.post(slack_webhook, json={"text": message}, timeout=5)
                print("✅ Cookie warning sent to Slack")
            except:
                print(message)
        else:
            print(message)
    
    def run_daemon(self, interval_hours: int = 6):
        """Run health monitor as daemon process."""
        print(f"🚀 Starting Health Monitor daemon (checking every {interval_hours} hours)")
        print(f"📝 Logs: {self.health_log}")
        print(f"Press Ctrl+C to stop\n")
        
        # Run immediately on start
        self.run_health_check()
        
        # Schedule periodic checks
        schedule.every(interval_hours).hours.do(self.run_health_check)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            print("\n\n👋 Health Monitor stopped")
    
    def get_health_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get health summary for last N days."""
        if not self.health_log.exists():
            return {"error": "No health log found"}
        
        cutoff = datetime.now() - timedelta(days=days)
        checks = []
        
        with open(self.health_log, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    timestamp = datetime.fromisoformat(entry['timestamp'])
                    if timestamp >= cutoff:
                        checks.append(entry)
                except:
                    continue
        
        if not checks:
            return {"error": f"No health checks in last {days} days"}
        
        # Calculate uptime per service
        service_stats = {}
        for check in checks:
            for service, result in check['results'].items():
                if service not in service_stats:
                    service_stats[service] = {"total": 0, "success": 0}
                
                service_stats[service]["total"] += 1
                if result.get("success"):
                    service_stats[service]["success"] += 1
        
        # Calculate uptime percentages
        uptime = {}
        for service, stats in service_stats.items():
            uptime[service] = {
                "uptime_pct": (stats["success"] / stats["total"]) * 100,
                "total_checks": stats["total"],
                "successful_checks": stats["success"]
            }
        
        return {
            "period_days": days,
            "total_checks": len(checks),
            "uptime_by_service": uptime,
            "latest_check": checks[-1] if checks else None
        }


def main():
    parser = argparse.ArgumentParser(description="Alpha Swarm Health Monitor")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (continuous monitoring)")
    parser.add_argument("--once", action="store_true", help="Run single health check")
    parser.add_argument("--interval", type=int, default=6, help="Check interval in hours (default: 6)")
    parser.add_argument("--summary", type=int, metavar="DAYS", help="Show health summary for last N days")
    parser.add_argument("--update-linkedin-rotation", action="store_true", help="Update LinkedIn cookie rotation timestamp")
    
    args = parser.parse_args()
    
    monitor = HealthMonitor()
    
    if args.update_linkedin_rotation:
        monitor.update_linkedin_rotation()
    elif args.summary:
        summary = monitor.get_health_summary(days=args.summary)
        print(json.dumps(summary, indent=2))
    elif args.daemon:
        monitor.run_daemon(interval_hours=args.interval)
    else:
        # Default: run once
        monitor.run_health_check()


if __name__ == "__main__":
    main()
