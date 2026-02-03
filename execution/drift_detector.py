#!/usr/bin/env python3
"""
Drift Detector & Assurance Monitor
==================================
Detects out-of-distribution shifts and verifies system assurance cases.

Features:
- Distribution drift detection (PSI, mean shift, variance change)
- Dynamic assurance case verification
- Environmental change monitoring
- Automatic alerting and remediation

Usage:
    from execution.drift_detector import DriftDetector, DynamicAssurance
"""

import os
import sys
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict, field
from collections import deque
import statistics

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

console = Console()


@dataclass
class DriftResult:
    """Result of drift detection."""
    feature: str
    has_drift: bool
    drift_type: Optional[str]
    severity: str  # low, medium, high, critical
    baseline_value: float
    current_value: float
    threshold: float
    detected_at: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class AssuranceCaseResult:
    """Result of assurance case verification."""
    name: str
    claim: str
    passed: bool
    evidence: Any
    threshold_min: Optional[float]
    threshold_max: Optional[float]
    verified_at: str
    action_taken: Optional[str] = None


class DriftDetector:
    """
    Detects distribution drift in system metrics and lead characteristics.
    
    Uses multiple detection methods:
    - Population Stability Index (PSI)
    - Mean shift detection
    - Variance change detection
    - Range violations
    """
    
    PSI_THRESHOLDS = {
        "low": 0.1,
        "medium": 0.2,
        "high": 0.25
    }
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.baseline_stats: Dict[str, Dict[str, float]] = {}
        self.current_windows: Dict[str, deque] = {}
        self.drift_history: List[DriftResult] = []
        self.alert_callbacks: List[Callable] = []
        
        self._load_baselines()
    
    def set_baseline(self, feature: str, values: List[float]):
        """Set baseline distribution for a feature."""
        
        if not values:
            return
        
        self.baseline_stats[feature] = {
            "mean": statistics.mean(values),
            "std": statistics.stdev(values) if len(values) > 1 else 0.0,
            "min": min(values),
            "max": max(values),
            "median": statistics.median(values),
            "sample_size": len(values),
            "set_at": datetime.utcnow().isoformat()
        }
        
        # Create histogram buckets
        if len(values) >= 10:
            sorted_values = sorted(values)
            n_buckets = min(20, len(values) // 5)
            bucket_size = len(values) // n_buckets
            
            buckets = []
            for i in range(n_buckets):
                start_idx = i * bucket_size
                end_idx = start_idx + bucket_size if i < n_buckets - 1 else len(values)
                bucket_values = sorted_values[start_idx:end_idx]
                buckets.append({
                    "min": bucket_values[0],
                    "max": bucket_values[-1],
                    "count": len(bucket_values),
                    "proportion": len(bucket_values) / len(values)
                })
            
            self.baseline_stats[feature]["buckets"] = buckets
        
        self._save_baselines()
        console.print(f"[dim]Set baseline for {feature}: mean={self.baseline_stats[feature]['mean']:.2f}[/dim]")
    
    def add_value(self, feature: str, value: float):
        """Add a new value to the current window."""
        
        if feature not in self.current_windows:
            self.current_windows[feature] = deque(maxlen=self.window_size)
        
        self.current_windows[feature].append(value)
    
    def check_drift(self, feature: str, values: List[float] = None) -> DriftResult:
        """
        Check for distribution drift in a feature.
        
        Args:
            feature: Name of the feature to check
            values: Optional list of values to check against baseline.
                   If not provided, uses current window.
        """
        
        if feature not in self.baseline_stats:
            return DriftResult(
                feature=feature,
                has_drift=False,
                drift_type=None,
                severity="low",
                baseline_value=0,
                current_value=0,
                threshold=0,
                detected_at=datetime.utcnow().isoformat(),
                details={"error": "No baseline set"}
            )
        
        if values is None:
            if feature not in self.current_windows:
                return DriftResult(
                    feature=feature,
                    has_drift=False,
                    drift_type=None,
                    severity="low",
                    baseline_value=0,
                    current_value=0,
                    threshold=0,
                    detected_at=datetime.utcnow().isoformat(),
                    details={"error": "No current values"}
                )
            values = list(self.current_windows[feature])
        
        if len(values) < 10:
            return DriftResult(
                feature=feature,
                has_drift=False,
                drift_type=None,
                severity="low",
                baseline_value=0,
                current_value=0,
                threshold=0,
                detected_at=datetime.utcnow().isoformat(),
                details={"error": "Insufficient data"}
            )
        
        baseline = self.baseline_stats[feature]
        drifts = []
        
        # 1. Mean shift detection
        current_mean = statistics.mean(values)
        baseline_mean = baseline["mean"]
        baseline_std = baseline["std"] or 1.0
        
        z_score = abs(current_mean - baseline_mean) / baseline_std
        if z_score > 2.0:
            drifts.append({
                "type": "mean_shift",
                "z_score": z_score,
                "severity": "high" if z_score > 3.0 else "medium"
            })
        
        # 2. Variance change detection
        current_std = statistics.stdev(values) if len(values) > 1 else 0.0
        variance_ratio = current_std / baseline_std if baseline_std > 0 else 1.0
        
        if variance_ratio < 0.5 or variance_ratio > 2.0:
            drifts.append({
                "type": "variance_change",
                "ratio": variance_ratio,
                "severity": "medium"
            })
        
        # 3. PSI calculation
        if "buckets" in baseline:
            psi = self._calculate_psi(baseline["buckets"], values)
            if psi > self.PSI_THRESHOLDS["low"]:
                severity = "low"
                if psi > self.PSI_THRESHOLDS["high"]:
                    severity = "high"
                elif psi > self.PSI_THRESHOLDS["medium"]:
                    severity = "medium"
                
                drifts.append({
                    "type": "distribution_shift",
                    "psi": psi,
                    "severity": severity
                })
        
        # 4. Range violations
        current_min = min(values)
        current_max = max(values)
        
        if current_min < baseline["min"] * 0.5 or current_max > baseline["max"] * 2.0:
            drifts.append({
                "type": "range_violation",
                "current_range": [current_min, current_max],
                "baseline_range": [baseline["min"], baseline["max"]],
                "severity": "medium"
            })
        
        # Determine overall result
        has_drift = len(drifts) > 0
        max_severity = max([d["severity"] for d in drifts], default="low")
        drift_type = drifts[0]["type"] if drifts else None
        
        result = DriftResult(
            feature=feature,
            has_drift=has_drift,
            drift_type=drift_type,
            severity=max_severity,
            baseline_value=baseline_mean,
            current_value=current_mean,
            threshold=2.0,
            detected_at=datetime.utcnow().isoformat(),
            details={"all_drifts": drifts}
        )
        
        if has_drift:
            self.drift_history.append(result)
            self._handle_drift(result)
        
        return result
    
    def _calculate_psi(self, baseline_buckets: List[Dict], current_values: List[float]) -> float:
        """Calculate Population Stability Index."""
        
        n_buckets = len(baseline_buckets)
        current_counts = [0] * n_buckets
        
        for value in current_values:
            for i, bucket in enumerate(baseline_buckets):
                if bucket["min"] <= value <= bucket["max"]:
                    current_counts[i] += 1
                    break
            else:
                # Value outside all buckets - assign to nearest
                if value < baseline_buckets[0]["min"]:
                    current_counts[0] += 1
                else:
                    current_counts[-1] += 1
        
        total = sum(current_counts)
        if total == 0:
            return 0.0
        
        psi = 0.0
        for i, bucket in enumerate(baseline_buckets):
            expected_prop = bucket["proportion"]
            actual_prop = current_counts[i] / total
            
            # Add small value to avoid log(0)
            expected_prop = max(expected_prop, 0.0001)
            actual_prop = max(actual_prop, 0.0001)
            
            psi += (actual_prop - expected_prop) * math.log(actual_prop / expected_prop)
        
        return psi
    
    def _handle_drift(self, result: DriftResult):
        """Handle detected drift."""
        
        console.print(f"[yellow]⚠️ Drift detected in {result.feature}: {result.drift_type} ({result.severity})[/yellow]")
        
        # Notify callbacks
        for callback in self.alert_callbacks:
            try:
                callback(result)
            except Exception as e:
                console.print(f"[red]Alert callback error: {e}[/red]")
        
        # Auto-remediation for high severity
        if result.severity == "high":
            self._trigger_remediation(result)
    
    def _trigger_remediation(self, result: DriftResult):
        """Trigger automatic remediation for high-severity drift."""
        
        console.print(f"[red]🔧 Triggering remediation for {result.feature}[/red]")
        
        # Log for later analysis
        remediation_log = {
            "drift": asdict(result),
            "action": "baseline_refresh_scheduled",
            "triggered_at": datetime.utcnow().isoformat()
        }
        
        log_path = Path(__file__).parent.parent / ".hive-mind" / "remediation_log.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        existing = []
        if log_path.exists():
            with open(log_path) as f:
                existing = json.load(f)
        
        existing.append(remediation_log)
        
        with open(log_path, "w") as f:
            json.dump(existing[-100:], f, indent=2)
    
    def register_alert_callback(self, callback: Callable[[DriftResult], None]):
        """Register a callback for drift alerts."""
        self.alert_callbacks.append(callback)
    
    def _save_baselines(self):
        """Save baselines to disk."""
        path = Path(__file__).parent.parent / ".hive-mind" / "drift_baselines.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w") as f:
            json.dump(self.baseline_stats, f, indent=2)
    
    def _load_baselines(self):
        """Load baselines from disk."""
        path = Path(__file__).parent.parent / ".hive-mind" / "drift_baselines.json"
        
        if path.exists():
            try:
                with open(path) as f:
                    self.baseline_stats = json.load(f)
                console.print(f"[dim]Loaded {len(self.baseline_stats)} drift baselines[/dim]")
            except Exception:
                pass


class DynamicAssurance:
    """
    Self-reverifying system that continuously validates assumptions
    and triggers actions when assurance cases fail.
    """
    
    def __init__(self):
        self.assurance_cases: Dict[str, Dict] = {}
        self.verification_history: List[AssuranceCaseResult] = []
        self.alerts: List[Dict] = []
        
        self._load_cases()
    
    def define_case(self, name: str, 
                    claim: str,
                    evidence_collector: Callable[[], Any],
                    threshold_min: float = None,
                    threshold_max: float = None,
                    action: str = "notify",
                    severity: str = "warning"):
        """
        Define an assurance case.
        
        Args:
            name: Unique identifier for the case
            claim: What we're asserting
            evidence_collector: Function that returns evidence value
            threshold_min: Minimum acceptable value
            threshold_max: Maximum acceptable value
            action: What to do on violation (notify, pause, reduce_throughput)
            severity: warning, error, critical
        """
        
        self.assurance_cases[name] = {
            "claim": claim,
            "evidence_collector": evidence_collector,
            "threshold_min": threshold_min,
            "threshold_max": threshold_max,
            "action": action,
            "severity": severity,
            "last_verified": None,
            "status": "pending",
            "consecutive_failures": 0
        }
    
    def verify_case(self, name: str) -> AssuranceCaseResult:
        """Verify a specific assurance case."""
        
        if name not in self.assurance_cases:
            raise ValueError(f"Unknown assurance case: {name}")
        
        case = self.assurance_cases[name]
        
        try:
            evidence = case["evidence_collector"]()
            
            passed = True
            if case["threshold_min"] is not None and evidence < case["threshold_min"]:
                passed = False
            if case["threshold_max"] is not None and evidence > case["threshold_max"]:
                passed = False
            
            case["last_verified"] = datetime.utcnow().isoformat()
            case["status"] = "passed" if passed else "failed"
            
            if passed:
                case["consecutive_failures"] = 0
            else:
                case["consecutive_failures"] += 1
            
            result = AssuranceCaseResult(
                name=name,
                claim=case["claim"],
                passed=passed,
                evidence=evidence,
                threshold_min=case["threshold_min"],
                threshold_max=case["threshold_max"],
                verified_at=case["last_verified"]
            )
            
            self.verification_history.append(result)
            
            if not passed:
                self._handle_violation(name, case, evidence)
                result.action_taken = case["action"]
            
            return result
            
        except Exception as e:
            case["status"] = "error"
            case["last_verified"] = datetime.utcnow().isoformat()
            
            return AssuranceCaseResult(
                name=name,
                claim=case["claim"],
                passed=False,
                evidence=str(e),
                threshold_min=case["threshold_min"],
                threshold_max=case["threshold_max"],
                verified_at=case["last_verified"]
            )
    
    def verify_all(self) -> Dict[str, AssuranceCaseResult]:
        """Verify all assurance cases."""
        
        results = {}
        for name in self.assurance_cases:
            results[name] = self.verify_case(name)
        return results
    
    def _handle_violation(self, name: str, case: Dict, evidence: Any):
        """Handle assurance case violation."""
        
        alert = {
            "case": name,
            "claim": case["claim"],
            "evidence": evidence,
            "threshold_min": case["threshold_min"],
            "threshold_max": case["threshold_max"],
            "severity": case["severity"],
            "consecutive_failures": case["consecutive_failures"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.alerts.append(alert)
        
        console.print(f"[red]🚨 Assurance violation: {name}[/red]")
        console.print(f"[red]   Claim: {case['claim']}[/red]")
        console.print(f"[red]   Evidence: {evidence}, Threshold: [{case['threshold_min']}, {case['threshold_max']}][/red]")
        
        action = case["action"]
        if action == "pause":
            console.print("[yellow]   Action: Pausing operations[/yellow]")
            # Trigger pause via degradation manager
        elif action == "reduce_throughput":
            console.print("[yellow]   Action: Reducing throughput[/yellow]")
        elif action == "notify":
            console.print("[yellow]   Action: Team notified[/yellow]")
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall assurance status."""
        
        statuses = {name: case["status"] for name, case in self.assurance_cases.items()}
        all_passed = all(s == "passed" for s in statuses.values())
        
        return {
            "healthy": all_passed,
            "cases": statuses,
            "recent_alerts": self.alerts[-10:],
            "checked_at": datetime.utcnow().isoformat()
        }
    
    def print_status(self):
        """Print assurance status table."""
        
        table = Table(title="Assurance Case Status")
        table.add_column("Case", style="cyan")
        table.add_column("Claim", style="dim")
        table.add_column("Status", style="green")
        table.add_column("Last Verified")
        
        for name, case in self.assurance_cases.items():
            status_color = "green" if case["status"] == "passed" else "red"
            table.add_row(
                name,
                case["claim"][:40] + "..." if len(case["claim"]) > 40 else case["claim"],
                f"[{status_color}]{case['status'].upper()}[/{status_color}]",
                case["last_verified"] or "Never"
            )
        
        console.print(table)
    
    def _save_cases(self):
        """Save case statuses (not collectors, they're functions)."""
        path = Path(__file__).parent.parent / ".hive-mind" / "assurance_status.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        
        save_data = {
            name: {
                "claim": case["claim"],
                "threshold_min": case["threshold_min"],
                "threshold_max": case["threshold_max"],
                "action": case["action"],
                "severity": case["severity"],
                "status": case["status"],
                "last_verified": case["last_verified"],
                "consecutive_failures": case["consecutive_failures"]
            }
            for name, case in self.assurance_cases.items()
        }
        
        with open(path, "w") as f:
            json.dump(save_data, f, indent=2)
    
    def _load_cases(self):
        """Load saved case statuses."""
        path = Path(__file__).parent.parent / ".hive-mind" / "assurance_status.json"
        
        if path.exists():
            try:
                with open(path) as f:
                    saved = json.load(f)
                # Cases need to be re-registered with collectors
                console.print(f"[dim]Found {len(saved)} saved assurance case statuses[/dim]")
            except Exception:
                pass


# Pre-built assurance case factory
def create_standard_assurance_cases(assurance: DynamicAssurance):
    """Create standard assurance cases for Alpha Swarm."""
    
    # These would normally call actual monitoring functions
    def get_email_deliverability():
        # Placeholder - would query Instantly API
        return 0.96
    
    def get_enrichment_rate():
        # Placeholder - would calculate from recent enrichments
        return 0.85
    
    def get_icp_match_rate():
        # Placeholder - would calculate from recent leads
        return 0.62
    
    def get_ae_approval_rate():
        # Placeholder - would query gatekeeper stats
        return 0.88
    
    def get_response_rate():
        # Placeholder - would query Instantly analytics
        return 0.08
    
    # Define cases
    assurance.define_case(
        "email_deliverability",
        "Email deliverability remains above 95%",
        get_email_deliverability,
        threshold_min=0.95,
        action="pause",
        severity="critical"
    )
    
    assurance.define_case(
        "enrichment_success",
        "Lead enrichment success rate above 80%",
        get_enrichment_rate,
        threshold_min=0.80,
        action="notify",
        severity="warning"
    )
    
    assurance.define_case(
        "icp_match",
        "ICP match rate above 50%",
        get_icp_match_rate,
        threshold_min=0.50,
        action="notify",
        severity="warning"
    )
    
    assurance.define_case(
        "ae_approval",
        "AE campaign approval rate above 80%",
        get_ae_approval_rate,
        threshold_min=0.80,
        action="notify",
        severity="warning"
    )
    
    assurance.define_case(
        "response_rate",
        "Email response rate above 5%",
        get_response_rate,
        threshold_min=0.05,
        action="reduce_throughput",
        severity="error"
    )


if __name__ == "__main__":
    console.print("[bold]Drift Detector & Assurance Monitor Demo[/bold]\n")
    
    # Demo drift detection
    detector = DriftDetector()
    
    # Set baseline
    baseline_values = [50 + i * 0.1 for i in range(100)]
    detector.set_baseline("icp_score", baseline_values)
    
    # Check for drift with shifted values
    shifted_values = [65 + i * 0.1 for i in range(100)]  # Mean shifted
    result = detector.check_drift("icp_score", shifted_values)
    
    console.print(f"Drift result: {asdict(result)}")
    
    # Demo assurance cases
    console.print("\n[bold]Assurance Cases[/bold]\n")
    
    assurance = DynamicAssurance()
    create_standard_assurance_cases(assurance)
    
    # Verify all
    results = assurance.verify_all()
    assurance.print_status()
