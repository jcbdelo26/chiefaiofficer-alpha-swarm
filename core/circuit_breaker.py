"""
Circuit Breaker pattern implementation to stop operations when failures exceed thresholds.
Prevents cascading failures by temporarily blocking calls to failing services.
"""

import json
import functools
import asyncio
from enum import Enum
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Callable, Any

try:
    from core.alerts import send_critical, send_info
    _ALERTS_AVAILABLE = True
except ImportError:
    _ALERTS_AVAILABLE = False


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocked, failures exceeded threshold
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Individual circuit breaker for a service."""
    name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    failure_threshold: int = 5
    recovery_timeout_seconds: int = 60
    half_open_max_calls: int = 3
    half_open_call_count: int = 0
    
    def to_dict(self) -> Dict:
        """Convert to serializable dictionary."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout_seconds,
            "half_open_max_calls": self.half_open_max_calls,
            "half_open_call_count": self.half_open_call_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CircuitBreaker":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            state=CircuitState(data["state"]),
            failure_count=data["failure_count"],
            success_count=data["success_count"],
            last_failure_time=datetime.fromisoformat(data["last_failure_time"]) if data["last_failure_time"] else None,
            failure_threshold=data["failure_threshold"],
            recovery_timeout_seconds=data["recovery_timeout_seconds"],
            half_open_max_calls=data["half_open_max_calls"],
            half_open_call_count=data.get("half_open_call_count", 0)
        )


class CircuitBreakerError(Exception):
    """Raised when circuit is open and call is blocked."""
    def __init__(self, breaker_name: str, time_until_retry: Optional[float] = None):
        self.breaker_name = breaker_name
        self.time_until_retry = time_until_retry
        msg = f"Circuit breaker '{breaker_name}' is OPEN"
        if time_until_retry:
            msg += f" - retry in {time_until_retry:.1f}s"
        super().__init__(msg)


class CircuitBreakerRegistry:
    """Registry managing all circuit breakers."""
    
    def __init__(self, state_file: Optional[Path] = None):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.state_file = state_file or Path(".hive-mind/circuit_breakers.json")
        self._load_state()
        self._register_defaults()
    
    def _register_defaults(self):
        """Register pre-configured breakers."""
        defaults = [
            ("ghl_api", 5, 60),
            ("linkedin_api", 3, 300),
            ("supabase", 5, 30),
            ("clay_api", 5, 120),
            ("email_sending", 3, 600),
        ]
        for name, threshold, timeout in defaults:
            if name not in self.breakers:
                self.register(name, threshold, timeout)
    
    def _load_state(self):
        """Load persisted state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                for breaker_data in data.get("breakers", []):
                    breaker = CircuitBreaker.from_dict(breaker_data)
                    self.breakers[breaker.name] = breaker
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[CircuitBreaker] Failed to load state: {e}")
    
    def _save_state(self):
        """Persist state to file."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "breakers": [b.to_dict() for b in self.breakers.values()],
            "updated_at": datetime.now().isoformat()
        }
        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def register(self, name: str, failure_threshold: int = 5, 
                 recovery_timeout: int = 60, half_open_max_calls: int = 3) -> CircuitBreaker:
        """Register a new circuit breaker."""
        if name in self.breakers:
            return self.breakers[name]
        
        breaker = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout_seconds=recovery_timeout,
            half_open_max_calls=half_open_max_calls
        )
        self.breakers[name] = breaker
        self._save_state()
        return breaker
    
    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        return self.breakers.get(name)
    
    def _check_recovery(self, breaker: CircuitBreaker) -> bool:
        """Check if breaker should transition from OPEN to HALF_OPEN."""
        if breaker.state != CircuitState.OPEN:
            return False
        
        if breaker.last_failure_time is None:
            return True
        
        elapsed = (datetime.now() - breaker.last_failure_time).total_seconds()
        if elapsed >= breaker.recovery_timeout_seconds:
            breaker.state = CircuitState.HALF_OPEN
            breaker.half_open_call_count = 0
            self._save_state()
            print(f"[CircuitBreaker] {breaker.name}: OPEN -> HALF_OPEN (testing recovery)")
            return True
        return False
    
    def record_success(self, name: str):
        """Record a successful call."""
        breaker = self.breakers.get(name)
        if not breaker:
            return
        
        breaker.success_count += 1
        
        if breaker.state == CircuitState.HALF_OPEN:
            breaker.half_open_call_count += 1
            if breaker.half_open_call_count >= breaker.half_open_max_calls:
                breaker.state = CircuitState.CLOSED
                breaker.failure_count = 0
                breaker.half_open_call_count = 0
                print(f"[CircuitBreaker] {breaker.name}: HALF_OPEN -> CLOSED (recovered)")
                if _ALERTS_AVAILABLE:
                    send_info(
                        f"Circuit breaker recovered: {breaker.name}",
                        f"Service '{breaker.name}' has recovered after "
                        f"{breaker.half_open_max_calls} successful calls.",
                        source="circuit_breaker",
                    )
        elif breaker.state == CircuitState.CLOSED:
            breaker.failure_count = 0
        
        self._save_state()
    
    def record_failure(self, name: str, error: Optional[Exception] = None):
        """Record a failed call."""
        breaker = self.breakers.get(name)
        if not breaker:
            return
        
        breaker.failure_count += 1
        breaker.last_failure_time = datetime.now()
        
        if breaker.state == CircuitState.HALF_OPEN:
            breaker.state = CircuitState.OPEN
            print(f"[CircuitBreaker] {breaker.name}: HALF_OPEN -> OPEN (failure during recovery)")
            if _ALERTS_AVAILABLE:
                send_critical(
                    f"Circuit breaker re-opened: {breaker.name}",
                    f"Service '{breaker.name}' failed during recovery "
                    f"(HALF_OPEN -> OPEN). Retry in "
                    f"{breaker.recovery_timeout_seconds}s.",
                    metadata={"service": breaker.name,
                              "failure_count": breaker.failure_count},
                    source="circuit_breaker",
                )
        elif breaker.state == CircuitState.CLOSED:
            if breaker.failure_count >= breaker.failure_threshold:
                breaker.state = CircuitState.OPEN
                print(f"[CircuitBreaker] {breaker.name}: CLOSED -> OPEN "
                      f"(failures: {breaker.failure_count}/{breaker.failure_threshold})")
                if _ALERTS_AVAILABLE:
                    send_critical(
                        f"Circuit breaker OPEN: {breaker.name}",
                        f"Service '{breaker.name}' exceeded failure threshold "
                        f"({breaker.failure_count}/{breaker.failure_threshold}). "
                        f"Blocked for {breaker.recovery_timeout_seconds}s.",
                        metadata={"service": breaker.name,
                                  "failure_count": breaker.failure_count,
                                  "threshold": breaker.failure_threshold},
                        source="circuit_breaker",
                    )
        
        if error:
            print(f"[CircuitBreaker] {breaker.name} failure: {type(error).__name__}: {error}")
        
        self._save_state()
    
    def is_available(self, name: str) -> bool:
        """Check if a service is available (circuit not open)."""
        breaker = self.breakers.get(name)
        if not breaker:
            return True
        
        if breaker.state == CircuitState.CLOSED:
            return True
        
        if breaker.state == CircuitState.OPEN:
            self._check_recovery(breaker)
            return breaker.state != CircuitState.OPEN
        
        if breaker.state == CircuitState.HALF_OPEN:
            return True
        
        return True
    
    def get_time_until_retry(self, name: str) -> Optional[float]:
        """Get seconds until circuit may transition to HALF_OPEN."""
        breaker = self.breakers.get(name)
        if not breaker or breaker.state != CircuitState.OPEN:
            return None
        
        if breaker.last_failure_time is None:
            return 0
        
        elapsed = (datetime.now() - breaker.last_failure_time).total_seconds()
        remaining = breaker.recovery_timeout_seconds - elapsed
        return max(0, remaining)
    
    def get_status(self) -> Dict[str, Dict]:
        """Get status of all circuit breakers."""
        status = {}
        for name, breaker in self.breakers.items():
            self._check_recovery(breaker)
            status[name] = {
                "state": breaker.state.value,
                "failure_count": breaker.failure_count,
                "success_count": breaker.success_count,
                "failure_threshold": breaker.failure_threshold,
                "recovery_timeout_seconds": breaker.recovery_timeout_seconds,
                "time_until_retry": self.get_time_until_retry(name)
            }
        return status
    
    def force_open(self, name: str):
        """Manually open a circuit breaker."""
        breaker = self.breakers.get(name)
        if breaker:
            breaker.state = CircuitState.OPEN
            breaker.last_failure_time = datetime.now()
            self._save_state()
            print(f"[CircuitBreaker] {name}: Manually OPENED")
    
    def force_close(self, name: str):
        """Manually close (reset) a circuit breaker."""
        breaker = self.breakers.get(name)
        if breaker:
            breaker.state = CircuitState.CLOSED
            breaker.failure_count = 0
            breaker.half_open_call_count = 0
            self._save_state()
            print(f"[CircuitBreaker] {name}: Manually CLOSED (reset)")


# Global registry instance
_registry: Optional[CircuitBreakerRegistry] = None


def get_registry() -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry."""
    global _registry
    if _registry is None:
        _registry = CircuitBreakerRegistry()
    return _registry


def with_circuit_breaker(breaker_name: str, fallback: Optional[Callable] = None):
    """
    Decorator to wrap a function with circuit breaker protection.
    
    Args:
        breaker_name: Name of the circuit breaker to use
        fallback: Optional fallback function to call when circuit is open
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            registry = get_registry()
            
            if not registry.is_available(breaker_name):
                time_until_retry = registry.get_time_until_retry(breaker_name)
                if fallback:
                    return await fallback(*args, **kwargs) if asyncio.iscoroutinefunction(fallback) else fallback(*args, **kwargs)
                raise CircuitBreakerError(breaker_name, time_until_retry)
            
            try:
                result = await func(*args, **kwargs)
                registry.record_success(breaker_name)
                return result
            except Exception as e:
                registry.record_failure(breaker_name, e)
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            registry = get_registry()
            
            if not registry.is_available(breaker_name):
                time_until_retry = registry.get_time_until_retry(breaker_name)
                if fallback:
                    return fallback(*args, **kwargs)
                raise CircuitBreakerError(breaker_name, time_until_retry)
            
            try:
                result = func(*args, **kwargs)
                registry.record_success(breaker_name)
                return result
            except Exception as e:
                registry.record_failure(breaker_name, e)
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


async def main():
    """Simulate circuit breaker behavior with failures and recovery."""
    import random
    
    print("=" * 60)
    print("Circuit Breaker Simulation")
    print("=" * 60)
    
    registry = get_registry()
    
    print("\n--- Initial Status ---")
    for name, status in registry.get_status().items():
        print(f"  {name}: {status['state']}")
    
    @with_circuit_breaker("ghl_api")
    async def call_ghl_api(success: bool = True):
        if not success:
            raise ConnectionError("GHL API timeout")
        return {"status": "ok"}
    
    @with_circuit_breaker("linkedin_api")
    async def call_linkedin_api(success: bool = True):
        if not success:
            raise ConnectionError("LinkedIn rate limited")
        return {"status": "ok"}
    
    print("\n--- Simulating GHL API failures (threshold: 5) ---")
    for i in range(6):
        try:
            await call_ghl_api(success=False)
        except ConnectionError as e:
            print(f"  Call {i+1}: Failed - {e}")
        except CircuitBreakerError as e:
            print(f"  Call {i+1}: BLOCKED - {e}")
    
    print("\n--- GHL Status after failures ---")
    status = registry.get_status()["ghl_api"]
    print(f"  State: {status['state']}")
    print(f"  Failures: {status['failure_count']}/{status['failure_threshold']}")
    print(f"  Retry in: {status['time_until_retry']:.1f}s")
    
    print("\n--- Simulating LinkedIn API failures (threshold: 3) ---")
    for i in range(4):
        try:
            await call_linkedin_api(success=False)
        except ConnectionError as e:
            print(f"  Call {i+1}: Failed - {e}")
        except CircuitBreakerError as e:
            print(f"  Call {i+1}: BLOCKED - {e}")
    
    print("\n--- Manual force close and recovery test ---")
    registry.force_close("ghl_api")
    
    print("\n  Testing successful calls...")
    for i in range(3):
        try:
            result = await call_ghl_api(success=True)
            print(f"  Call {i+1}: Success - {result}")
        except Exception as e:
            print(f"  Call {i+1}: Error - {e}")
    
    print("\n--- Final Status ---")
    for name, status in registry.get_status().items():
        print(f"  {name}:")
        print(f"    State: {status['state']}")
        print(f"    Failures: {status['failure_count']}/{status['failure_threshold']}")
        print(f"    Successes: {status['success_count']}")
    
    print("\n--- Simulating HALF_OPEN recovery ---")
    registry.register("test_service", failure_threshold=2, recovery_timeout=2, half_open_max_calls=2)
    
    @with_circuit_breaker("test_service")
    async def call_test_service(success: bool = True):
        if not success:
            raise RuntimeError("Test service error")
        return {"ok": True}
    
    print("  Causing failures to open circuit...")
    for i in range(3):
        try:
            await call_test_service(success=False)
        except (RuntimeError, CircuitBreakerError) as e:
            print(f"    Failure {i+1}: {type(e).__name__}")
    
    print(f"  State: {registry.get_status()['test_service']['state']}")
    
    print("  Waiting for recovery timeout (2s)...")
    await asyncio.sleep(2.5)
    
    registry.is_available("test_service")
    print(f"  State after timeout: {registry.get_status()['test_service']['state']}")
    
    print("  Making successful calls in HALF_OPEN...")
    for i in range(2):
        try:
            await call_test_service(success=True)
            print(f"    Success {i+1}")
        except Exception as e:
            print(f"    Error: {e}")
    
    print(f"  Final state: {registry.get_status()['test_service']['state']}")
    
    print("\n" + "=" * 60)
    print("Simulation complete. State saved to .hive-mind/circuit_breakers.json")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
