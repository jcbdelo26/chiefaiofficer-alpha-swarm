"""
Full Knowledge Ingestion Orchestrator
Runs all ingestion scripts in sequence for production readiness.
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
LOG_DIR = PROJECT_ROOT / ".tmp" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


class IngestionOrchestrator:
    """Orchestrates full knowledge ingestion for production readiness."""
    
    def __init__(self):
        self.log_file = LOG_DIR / f"full_ingestion_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.log"
        self.results = {
            "started_at": datetime.now().isoformat(),
            "steps": [],
            "success": True,
            "errors": []
        }
        
    def _log(self, message: str, level: str = "INFO"):
        """Log message to file and console."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"{timestamp} | {level} | {message}"
        print(log_line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    
    def _run_script(self, script_name: str, args: List[str] = None) -> bool:
        """Run a Python script and capture output."""
        script_path = PROJECT_ROOT / "execution" / script_name
        
        if not script_path.exists():
            self._log(f"Script not found: {script_path}", "ERROR")
            return False
        
        cmd = [sys.executable, str(script_path)]
        if args:
            cmd.extend(args)
        
        self._log(f"Running: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            # Log output
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    self._log(f"  {line}")
            
            if result.returncode != 0:
                self._log(f"Script failed with code {result.returncode}", "ERROR")
                if result.stderr:
                    self._log(f"  Error: {result.stderr[:500]}", "ERROR")
                return False
            
            return True
            
        except subprocess.TimeoutExpired:
            self._log("Script timed out", "ERROR")
            return False
        except Exception as e:
            self._log(f"Failed to run script: {e}", "ERROR")
            return False
    
    def check_prerequisites(self) -> Dict[str, bool]:
        """Check which APIs are configured."""
        prereqs = {
            "instantly": bool(os.getenv("INSTANTLY_API_KEY")),
            "ghl": bool(os.getenv("GHL_API_KEY") and os.getenv("GHL_LOCATION_ID")),
            "clay": bool(os.getenv("CLAY_API_KEY")),
        }
        
        self._log("Checking prerequisites...")
        for api, configured in prereqs.items():
            status = "✓" if configured else "✗"
            self._log(f"  {status} {api.upper()}: {'Configured' if configured else 'Not configured'}")
        
        return prereqs
    
    def run_step(self, name: str, script: str, args: List[str] = None, required: bool = True) -> bool:
        """Run an ingestion step."""
        step = {
            "name": name,
            "script": script,
            "started_at": datetime.now().isoformat(),
            "success": False,
            "skipped": False
        }
        
        self._log(f"\n{'='*60}")
        self._log(f"STEP: {name}")
        self._log(f"{'='*60}")
        
        success = self._run_script(script, args)
        
        step["completed_at"] = datetime.now().isoformat()
        step["success"] = success
        
        self.results["steps"].append(step)
        
        if not success:
            self.results["errors"].append(f"{name} failed")
            if required:
                self.results["success"] = False
        
        return success
    
    def run_full_ingestion(self, skip_missing_apis: bool = True) -> Dict[str, Any]:
        """Run complete ingestion pipeline."""
        self._log("\n" + "="*60)
        self._log("FULL KNOWLEDGE INGESTION STARTING")
        self._log("="*60 + "\n")
        
        prereqs = self.check_prerequisites()
        
        # Step 1: Instantly Campaign Analytics
        if prereqs["instantly"]:
            self.run_step(
                "Instantly Campaign Analytics",
                "ingest_instantly_analytics.py",
                ["--days", "90"]
            )
        elif not skip_missing_apis:
            self._log("Skipping Instantly (not configured)", "WARN")
        
        # Step 2: Instantly Templates
        if prereqs["instantly"]:
            self.run_step(
                "Instantly Email Templates",
                "ingest_instantly_templates.py",
                ["--min-open-rate", "0.4"]
            )
        
        # Step 3: GHL Deals
        if prereqs["ghl"]:
            self.run_step(
                "GoHighLevel Deals",
                "ingest_ghl_deals.py",
                ["--days", "180"]
            )
        elif not skip_missing_apis:
            self._log("Skipping GHL (not configured)", "WARN")
        
        # Step 4: ICP Calibration (if deal data available)
        deals_dir = PROJECT_ROOT / ".hive-mind" / "knowledge" / "deals"
        if deals_dir.exists() and list(deals_dir.glob("*.json")):
            self.run_step(
                "ICP Calibration",
                "icp_calibrate.py",
                ["--calibrate"],
                required=False  # Optional step
            )
        
        # Step 5: Generate AE Validation Template
        self.run_step(
            "Generate AE Validation Template",
            "icp_calibrate.py",
            ["--generate-template", "--num-leads", "50"],
            required=False
        )
        
        # Finalize results
        self.results["completed_at"] = datetime.now().isoformat()
        
        # Calculate duration
        started = datetime.fromisoformat(self.results["started_at"])
        completed = datetime.fromisoformat(self.results["completed_at"])
        self.results["duration_seconds"] = (completed - started).total_seconds()
        
        # Summary
        successful_steps = sum(1 for s in self.results["steps"] if s["success"])
        total_steps = len(self.results["steps"])
        
        self._log("\n" + "="*60)
        self._log("INGESTION COMPLETE")
        self._log("="*60)
        self._log(f"Steps: {successful_steps}/{total_steps} successful")
        self._log(f"Duration: {self.results['duration_seconds']:.1f} seconds")
        self._log(f"Log file: {self.log_file}")
        self._log("="*60 + "\n")
        
        # Save results
        results_file = LOG_DIR / f"ingestion_results_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(self.results, f, indent=2)
        
        return self.results


def print_step_by_step_guide():
    """Print a step-by-step guide for production readiness."""
    guide = """
╔══════════════════════════════════════════════════════════════════════════╗
║          PRODUCTION READINESS - STEP BY STEP GUIDE                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  PHASE 1: API CONFIGURATION (Prerequisites)                             ║
║  ─────────────────────────────────────────────────────────────────────── ║
║                                                                          ║
║  1. Open .env file and configure:                                        ║
║     • INSTANTLY_API_KEY    - From Instantly.ai dashboard                 ║
║     • GHL_API_KEY          - From GoHighLevel settings                   ║
║     • GHL_LOCATION_ID      - Your GHL location ID                        ║
║     • SLACK_WEBHOOK_URL    - From Slack app settings                     ║
║                                                                          ║
║  2. Test connections:                                                    ║
║     python execution\\test_connections.py                                 ║
║                                                                          ║
║                                                                          ║
║  PHASE 2: DATA INGESTION                                                 ║
║  ─────────────────────────────────────────────────────────────────────── ║
║                                                                          ║
║  Option A: Run full ingestion (recommended)                              ║
║     python execution\\run_full_ingestion.py --full                        ║
║                                                                          ║
║  Option B: Run individual scripts                                        ║
║     1. python execution\\ingest_instantly_analytics.py --days 90          ║
║     2. python execution\\ingest_instantly_templates.py                    ║
║     3. python execution\\ingest_ghl_deals.py --days 180                   ║
║                                                                          ║
║                                                                          ║
║  PHASE 3: ICP CALIBRATION                                                ║
║  ─────────────────────────────────────────────────────────────────────── ║
║                                                                          ║
║  1. Generate AE validation template:                                     ║
║     python execution\\icp_calibrate.py --generate-template                ║
║                                                                          ║
║  2. Have AE review 50 leads in:                                          ║
║     .tmp\\ae_validation_template.json                                     ║
║                                                                          ║
║  3. Run calibration with feedback:                                       ║
║     python execution\\icp_calibrate.py --calibrate \\                      ║
║         --feedback .tmp\\ae_validation_template.json                      ║
║                                                                          ║
║                                                                          ║
║  PHASE 4: SCHEDULING SETUP                                               ║
║  ─────────────────────────────────────────────────────────────────────── ║
║                                                                          ║
║  See: directives\\deployment_framework.md for Windows Task Scheduler      ║
║  setup instructions.                                                     ║
║                                                                          ║
║                                                                          ║
║  PHASE 5: VERIFICATION                                                   ║
║  ─────────────────────────────────────────────────────────────────────── ║
║                                                                          ║
║  1. Check system health:                                                 ║
║     python execution\\health_check.py                                     ║
║                                                                          ║
║  2. Generate daily report:                                               ║
║     python execution\\generate_daily_report.py --print                    ║
║                                                                          ║
║  3. Test alert system:                                                   ║
║     python execution\\send_alert.py --test                                ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
    print(guide)


def main():
    parser = argparse.ArgumentParser(description="Full Knowledge Ingestion Orchestrator")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run full ingestion pipeline"
    )
    parser.add_argument(
        "--guide",
        action="store_true",
        help="Print step-by-step guide"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check prerequisites only"
    )
    parser.add_argument(
        "--skip-missing",
        action="store_true",
        default=True,
        help="Skip steps for unconfigured APIs"
    )
    
    args = parser.parse_args()
    
    if args.guide:
        print_step_by_step_guide()
        return
    
    orchestrator = IngestionOrchestrator()
    
    if args.check:
        orchestrator.check_prerequisites()
        return
    
    if args.full:
        results = orchestrator.run_full_ingestion(skip_missing_apis=args.skip_missing)
        print("\nResults Summary:")
        print(json.dumps({
            "success": results["success"],
            "steps_completed": len([s for s in results["steps"] if s["success"]]),
            "total_steps": len(results["steps"]),
            "duration_seconds": results.get("duration_seconds", 0),
            "errors": results.get("errors", [])
        }, indent=2))
        return
    
    # Default: print guide
    print_step_by_step_guide()


if __name__ == "__main__":
    main()
