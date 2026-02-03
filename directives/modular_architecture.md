# 🛡️ Modular Architecture with Fail-Safes & Reinforcement Learning
# Self-Reverifying Systems for Alpha Swarm

---

## Overview

This document defines the advanced modular architecture implementing:
1. **Fail-Safe Mechanisms** - Graceful degradation and error recovery
2. **Reinforcement Learning** - Adaptive decision-making from outcomes
3. **Dynamic Assurance Cases** - Self-reverifying systems for drift detection
4. **Out-of-Distribution Detection** - Environmental change monitoring

---

## 🏗️ Modular Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ALPHA SWARM CONTROL PLANE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │
│  │ CIRCUIT     │  │ RATE        │  │ HEALTH      │  │ DRIFT       │       │
│  │ BREAKER     │  │ LIMITER     │  │ MONITOR     │  │ DETECTOR    │       │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘       │
│         │                │                │                │              │
│         └────────────────┴────────────────┴────────────────┘              │
│                                    │                                       │
│                          ┌─────────┴─────────┐                            │
│                          │  ORCHESTRATOR     │                            │
│                          │  (Alpha Queen)    │                            │
│                          └─────────┬─────────┘                            │
│                                    │                                       │
│  ┌───────────────────────────────────────────────────────────────┐       │
│  │              REINFORCEMENT LEARNING ENGINE                     │       │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │       │
│  │  │ STATE       │  │ REWARD      │  │ POLICY      │           │       │
│  │  │ TRACKER     │→ │ CALCULATOR  │→ │ OPTIMIZER   │           │       │
│  │  └─────────────┘  └─────────────┘  └─────────────┘           │       │
│  └───────────────────────────────────────────────────────────────┘       │
│                                    │                                       │
│  ┌────────────┬────────────┬───────────────┬────────────┬───────────────┐ │
│  │            │            │               │            │               │ │
│  ▼            ▼            ▼               ▼            ▼               │ │
│ HUNTER    ENRICHER    SEGMENTOR       CRAFTER     GATEKEEPER           │ │
│ Agent     Agent       Agent           Agent       Agent                 │ │
│  │            │            │               │            │               │ │
│  └────────────┴────────────┴───────────────┴────────────┘               │ │
│                                    │                                     │ │
│                          ┌─────────┴─────────┐                          │ │
│                          │ ASSURANCE LAYER   │                          │ │
│                          │ (Verification)    │                          │ │
│                          └───────────────────┘                          │ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔒 Fail-Safe Mechanisms

### 1. Circuit Breaker Pattern

```python
class CircuitBreaker:
    """
    Prevents cascading failures by stopping calls to failing services.
    
    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Service failing, calls blocked
    - HALF_OPEN: Testing if service recovered
    """
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
    
    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
            else:
                raise CircuitOpenError("Service temporarily unavailable")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        self.failure_count = 0
        self.state = "CLOSED"
    
    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
    
    def _should_attempt_reset(self):
        if self.last_failure_time is None:
            return True
        elapsed = (datetime.utcnow() - self.last_failure_time).seconds
        return elapsed >= self.recovery_timeout
```

### 2. Graceful Degradation

```python
class GracefulDegradation:
    """
    Maintains system operation with reduced functionality when components fail.
    """
    
    DEGRADATION_LEVELS = {
        0: "FULL_OPERATION",      # All systems operational
        1: "REDUCED_ENRICHMENT",  # Clay down, use cached data
        2: "SCRAPING_ONLY",       # Enrichment down, just scrape
        3: "READ_ONLY",           # APIs down, only serve cached
        4: "MAINTENANCE"          # Critical failure, queue only
    }
    
    def __init__(self):
        self.current_level = 0
        self.component_status = {}
    
    def check_component(self, component: str) -> bool:
        """Check if a component is healthy."""
        return self.component_status.get(component, {}).get("healthy", True)
    
    def adjust_operation(self, failed_component: str):
        """Adjust operation based on component failure."""
        
        degradation_map = {
            "clay_api": 1,
            "rb2b_api": 1,
            "linkedin_session": 2,
            "ghl_api": 3,
            "instantly_api": 3,
            "database": 4
        }
        
        new_level = degradation_map.get(failed_component, 0)
        self.current_level = max(self.current_level, new_level)
        
        return self.DEGRADATION_LEVELS[self.current_level]
    
    def get_available_operations(self) -> List[str]:
        """Get list of operations available at current degradation level."""
        
        operations_by_level = {
            0: ["scrape", "enrich", "segment", "campaign", "send"],
            1: ["scrape", "segment_cached", "campaign", "send"],
            2: ["scrape", "queue_for_later"],
            3: ["read_cached", "queue_for_later"],
            4: ["queue_only"]
        }
        
        return operations_by_level[self.current_level]
```

### 3. Retry with Exponential Backoff

```python
class RetryStrategy:
    """
    Intelligent retry mechanism with exponential backoff and jitter.
    """
    
    def __init__(self, 
                 max_retries: int = 5,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 exponential_base: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
    
    def execute_with_retry(self, func, *args, **kwargs):
        """Execute function with retry logic."""
        
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except RetryableError as e:
                last_exception = e
                delay = self._calculate_delay(attempt)
                
                # Log retry attempt
                log_retry(func.__name__, attempt + 1, delay, str(e))
                
                time.sleep(delay)
            except NonRetryableError:
                raise  # Don't retry these
        
        raise MaxRetriesExceeded(f"Failed after {self.max_retries} attempts", last_exception)
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        
        # Add jitter (±25%)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        delay += jitter
        
        return delay
```

---

## 🧠 Reinforcement Learning Engine

### State-Action-Reward Framework

```python
class RLEngine:
    """
    Reinforcement Learning engine for adaptive decision-making.
    
    Uses a simplified Q-learning approach to optimize:
    - Template selection
    - Timing decisions
    - Personalization depth
    - Channel selection
    """
    
    def __init__(self, learning_rate: float = 0.1, discount_factor: float = 0.95):
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.q_table = {}  # State -> Action -> Q-value
        self.episode_rewards = []
    
    def get_state(self, lead: dict, context: dict) -> str:
        """
        Encode current state as a string.
        
        State features:
        - ICP tier (1-4)
        - Intent score bucket (low/med/high)
        - Source type
        - Day of week
        - Time of day bucket
        """
        
        icp_tier = lead.get("icp_tier", "tier_4")
        intent_bucket = self._bucket_intent(lead.get("intent_score", 0))
        source_type = lead.get("source_type", "unknown")
        day_of_week = datetime.utcnow().weekday()
        time_bucket = self._bucket_time(datetime.utcnow().hour)
        
        return f"{icp_tier}|{intent_bucket}|{source_type}|{day_of_week}|{time_bucket}"
    
    def get_available_actions(self, state: str) -> List[str]:
        """Get available actions for a state."""
        
        return [
            "template_competitor_displacement",
            "template_event_followup",
            "template_thought_leadership",
            "template_community_outreach",
            "delay_immediate",
            "delay_next_day",
            "delay_optimal_time",
            "personalization_high",
            "personalization_medium",
            "personalization_low"
        ]
    
    def select_action(self, state: str, epsilon: float = 0.1) -> str:
        """
        Select action using epsilon-greedy strategy.
        
        - With probability epsilon: explore (random action)
        - With probability 1-epsilon: exploit (best known action)
        """
        
        if random.random() < epsilon:
            # Explore
            actions = self.get_available_actions(state)
            return random.choice(actions)
        else:
            # Exploit
            return self._get_best_action(state)
    
    def _get_best_action(self, state: str) -> str:
        """Get the best action for a state based on Q-values."""
        
        if state not in self.q_table:
            # No experience for this state, return default
            return "template_competitor_displacement"
        
        state_actions = self.q_table[state]
        return max(state_actions, key=state_actions.get)
    
    def update(self, state: str, action: str, reward: float, next_state: str):
        """
        Update Q-value using Q-learning update rule.
        
        Q(s, a) = Q(s, a) + α * (r + γ * max(Q(s', a')) - Q(s, a))
        """
        
        # Initialize if needed
        if state not in self.q_table:
            self.q_table[state] = {}
        if action not in self.q_table[state]:
            self.q_table[state][action] = 0.0
        
        # Get current Q-value
        current_q = self.q_table[state][action]
        
        # Get max Q-value for next state
        if next_state in self.q_table:
            max_next_q = max(self.q_table[next_state].values())
        else:
            max_next_q = 0.0
        
        # Calculate new Q-value
        new_q = current_q + self.learning_rate * (
            reward + self.discount_factor * max_next_q - current_q
        )
        
        self.q_table[state][action] = new_q
    
    def calculate_reward(self, outcome: dict) -> float:
        """
        Calculate reward from campaign outcome.
        
        Reward signals:
        - Email opened: +1
        - Email clicked: +3
        - Reply received: +10
        - Positive reply: +20
        - Meeting booked: +50
        - Deal closed: +100
        - Unsubscribe: -10
        - Spam report: -50
        - Bounce: -5
        """
        
        reward = 0.0
        
        # Positive rewards
        reward += outcome.get("opens", 0) * 1
        reward += outcome.get("clicks", 0) * 3
        reward += outcome.get("replies", 0) * 10
        reward += outcome.get("positive_replies", 0) * 20
        reward += outcome.get("meetings_booked", 0) * 50
        reward += outcome.get("deals_closed", 0) * 100
        
        # Negative rewards
        reward -= outcome.get("unsubscribes", 0) * 10
        reward -= outcome.get("spam_reports", 0) * 50
        reward -= outcome.get("bounces", 0) * 5
        
        return reward
    
    def _bucket_intent(self, score: int) -> str:
        if score >= 80:
            return "high"
        elif score >= 50:
            return "medium"
        else:
            return "low"
    
    def _bucket_time(self, hour: int) -> str:
        if 9 <= hour < 12:
            return "morning"
        elif 12 <= hour < 14:
            return "lunch"
        elif 14 <= hour < 17:
            return "afternoon"
        else:
            return "off_hours"
    
    def save_policy(self, path: Path):
        """Save learned policy to disk."""
        with open(path, "w") as f:
            json.dump({
                "q_table": self.q_table,
                "episode_rewards": self.episode_rewards,
                "saved_at": datetime.utcnow().isoformat()
            }, f, indent=2)
    
    def load_policy(self, path: Path):
        """Load policy from disk."""
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                self.q_table = data.get("q_table", {})
                self.episode_rewards = data.get("episode_rewards", [])
```

---

## 📊 Dynamic Assurance Cases

### Self-Reverification System

```python
class DynamicAssurance:
    """
    Self-reverifying system that continuously validates assumptions
    and detects when the system is operating outside known parameters.
    """
    
    def __init__(self):
        self.baseline_metrics = {}
        self.current_metrics = {}
        self.assurance_cases = {}
        self.alerts = []
    
    def define_assurance_case(self, name: str, case: dict):
        """
        Define an assurance case with:
        - Claim: What we're asserting
        - Evidence: How we verify it
        - Threshold: Acceptable bounds
        - Action: What to do if violated
        """
        
        self.assurance_cases[name] = {
            "claim": case["claim"],
            "evidence_collector": case["evidence_collector"],
            "threshold_min": case.get("threshold_min"),
            "threshold_max": case.get("threshold_max"),
            "action_on_violation": case["action"],
            "severity": case.get("severity", "warning"),
            "last_verified": None,
            "status": "pending"
        }
    
    def verify_all(self) -> Dict[str, bool]:
        """Verify all assurance cases."""
        
        results = {}
        
        for name, case in self.assurance_cases.items():
            try:
                # Collect evidence
                evidence = case["evidence_collector"]()
                
                # Check thresholds
                passed = True
                if case["threshold_min"] is not None and evidence < case["threshold_min"]:
                    passed = False
                if case["threshold_max"] is not None and evidence > case["threshold_max"]:
                    passed = False
                
                # Update status
                case["last_verified"] = datetime.utcnow().isoformat()
                case["status"] = "passed" if passed else "failed"
                case["last_evidence"] = evidence
                
                results[name] = passed
                
                # Take action if violated
                if not passed:
                    self._handle_violation(name, case, evidence)
                    
            except Exception as e:
                case["status"] = "error"
                case["error"] = str(e)
                results[name] = False
        
        return results
    
    def _handle_violation(self, name: str, case: dict, evidence: Any):
        """Handle assurance case violation."""
        
        alert = {
            "case": name,
            "claim": case["claim"],
            "evidence": evidence,
            "threshold_min": case["threshold_min"],
            "threshold_max": case["threshold_max"],
            "severity": case["severity"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.alerts.append(alert)
        
        # Execute action
        action = case["action_on_violation"]
        if callable(action):
            action(alert)
        elif action == "pause_operations":
            self._pause_operations()
        elif action == "notify_team":
            self._notify_team(alert)
        elif action == "reduce_throughput":
            self._reduce_throughput()

# Example assurance cases
assurance = DynamicAssurance()

assurance.define_assurance_case("email_deliverability", {
    "claim": "Email deliverability remains above 95%",
    "evidence_collector": lambda: get_deliverability_rate(),
    "threshold_min": 0.95,
    "action": "pause_operations",
    "severity": "critical"
})

assurance.define_assurance_case("enrichment_success_rate", {
    "claim": "Enrichment success rate remains above 80%",
    "evidence_collector": lambda: get_enrichment_success_rate(),
    "threshold_min": 0.80,
    "action": "notify_team",
    "severity": "warning"
})

assurance.define_assurance_case("icp_match_rate", {
    "claim": "ICP match rate remains above 50%",
    "evidence_collector": lambda: get_icp_match_rate(),
    "threshold_min": 0.50,
    "action": "review_icp_criteria",
    "severity": "warning"
})
```

---

## 🔍 Out-of-Distribution Detection

### Drift Detection System

```python
class DriftDetector:
    """
    Detects when the system is operating on data that differs
    significantly from training/baseline distributions.
    
    Monitors:
    - Feature distribution shifts
    - Prediction confidence drops
    - Performance degradation
    - Environmental changes
    """
    
    def __init__(self, sensitivity: float = 0.1):
        self.sensitivity = sensitivity
        self.baseline_distributions = {}
        self.current_window = []
        self.window_size = 1000
        self.drift_history = []
    
    def set_baseline(self, feature: str, values: List[float]):
        """Set baseline distribution for a feature."""
        
        self.baseline_distributions[feature] = {
            "mean": np.mean(values),
            "std": np.std(values),
            "min": np.min(values),
            "max": np.max(values),
            "histogram": np.histogram(values, bins=20),
            "sample_size": len(values)
        }
    
    def check_drift(self, feature: str, current_values: List[float]) -> Dict[str, Any]:
        """
        Check for distribution drift using multiple methods.
        
        Methods:
        1. Mean shift detection
        2. Variance change detection
        3. KS test for distribution comparison
        4. Population Stability Index (PSI)
        """
        
        if feature not in self.baseline_distributions:
            return {"error": f"No baseline for feature: {feature}"}
        
        baseline = self.baseline_distributions[feature]
        
        results = {
            "feature": feature,
            "timestamp": datetime.utcnow().isoformat(),
            "drifts_detected": []
        }
        
        # Mean shift
        current_mean = np.mean(current_values)
        mean_shift = abs(current_mean - baseline["mean"]) / (baseline["std"] + 1e-10)
        if mean_shift > 2.0:  # More than 2 standard deviations
            results["drifts_detected"].append({
                "type": "mean_shift",
                "baseline": baseline["mean"],
                "current": current_mean,
                "shift_magnitude": mean_shift
            })
        
        # Variance change
        current_std = np.std(current_values)
        variance_ratio = current_std / (baseline["std"] + 1e-10)
        if variance_ratio < 0.5 or variance_ratio > 2.0:
            results["drifts_detected"].append({
                "type": "variance_change",
                "baseline_std": baseline["std"],
                "current_std": current_std,
                "ratio": variance_ratio
            })
        
        # Calculate PSI
        psi = self._calculate_psi(baseline["histogram"], current_values)
        if psi > 0.2:  # Industry standard threshold
            results["drifts_detected"].append({
                "type": "distribution_shift",
                "psi": psi,
                "severity": "high" if psi > 0.25 else "medium"
            })
        
        results["has_drift"] = len(results["drifts_detected"]) > 0
        
        if results["has_drift"]:
            self.drift_history.append(results)
            self._handle_drift(results)
        
        return results
    
    def _calculate_psi(self, baseline_hist: tuple, current_values: List[float]) -> float:
        """Calculate Population Stability Index."""
        
        baseline_counts, bin_edges = baseline_hist
        current_counts, _ = np.histogram(current_values, bins=bin_edges)
        
        # Normalize to proportions
        baseline_props = baseline_counts / (np.sum(baseline_counts) + 1e-10)
        current_props = current_counts / (np.sum(current_counts) + 1e-10)
        
        # Add small value to avoid log(0)
        baseline_props = np.clip(baseline_props, 1e-10, 1)
        current_props = np.clip(current_props, 1e-10, 1)
        
        # PSI formula
        psi = np.sum((current_props - baseline_props) * np.log(current_props / baseline_props))
        
        return float(psi)
    
    def _handle_drift(self, drift_result: dict):
        """Handle detected drift."""
        
        # Log drift
        log_drift_event(drift_result)
        
        # Determine severity and action
        max_severity = "low"
        for drift in drift_result["drifts_detected"]:
            if drift.get("type") == "distribution_shift" and drift.get("severity") == "high":
                max_severity = "high"
            elif drift.get("type") == "mean_shift" and drift.get("shift_magnitude", 0) > 3:
                max_severity = "high"
        
        if max_severity == "high":
            # Trigger retraining or model refresh
            trigger_model_refresh(drift_result["feature"])
            
            # Notify team
            notify_team_of_drift(drift_result)
    
    def monitor_environmental_changes(self) -> Dict[str, Any]:
        """
        Monitor for environmental changes that might affect performance.
        
        Checks:
        - API response patterns
        - LinkedIn UI/API changes
        - Email deliverability changes
        - Competitor landscape shifts
        """
        
        changes = []
        
        # Check LinkedIn API patterns
        linkedin_check = self._check_linkedin_patterns()
        if linkedin_check["changed"]:
            changes.append(linkedin_check)
        
        # Check email patterns
        email_check = self._check_email_patterns()
        if email_check["changed"]:
            changes.append(email_check)
        
        # Check enrichment patterns
        enrichment_check = self._check_enrichment_patterns()
        if enrichment_check["changed"]:
            changes.append(enrichment_check)
        
        return {
            "checked_at": datetime.utcnow().isoformat(),
            "changes_detected": len(changes) > 0,
            "changes": changes
        }
```

---

## 📁 Implementation Files

Create these files in the `execution/` directory:

| File | Purpose |
|------|---------|
| `fail_safe_manager.py` | Circuit breaker and degradation |
| `rl_engine.py` | Reinforcement learning engine |
| `assurance_monitor.py` | Dynamic assurance verification |
| `drift_detector.py` | Distribution drift detection |
| `self_healing.py` | Automatic recovery procedures |

---

## 🔄 Integration with Agents

```python
# In each agent, wrap operations with fail-safes

class HunterAgent:
    def __init__(self):
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=300)
        self.retry_strategy = RetryStrategy(max_retries=3)
        self.rl_engine = RLEngine()
        self.drift_detector = DriftDetector()
    
    def scrape_with_failsafe(self, source: str, **kwargs):
        """Scrape with full fail-safe protection."""
        
        # Check circuit state
        try:
            return self.circuit_breaker.call(
                self.retry_strategy.execute_with_retry,
                self._do_scrape,
                source,
                **kwargs
            )
        except CircuitOpenError:
            # Fallback to cached data
            return self._get_cached_data(source)
        except MaxRetriesExceeded as e:
            # Log and alert
            self._handle_persistent_failure(source, e)
            raise
    
    def _do_scrape(self, source: str, **kwargs):
        """Actual scraping logic."""
        # ... scraping implementation
        pass
```

---

## 📊 Monitoring Dashboard

The system exposes metrics for monitoring:

| Metric | Type | Alert Threshold |
|--------|------|-----------------|
| `circuit_breaker_state` | Gauge | OPEN |
| `degradation_level` | Gauge | > 2 |
| `rl_avg_reward` | Gauge | < 0 |
| `drift_psi` | Gauge | > 0.2 |
| `assurance_failures` | Counter | > 0 |
| `retry_rate` | Rate | > 50% |
| `recovery_time` | Histogram | > 5 min |

---

*Architecture Version: 1.0*
*Last Updated: 2026-01-12*
