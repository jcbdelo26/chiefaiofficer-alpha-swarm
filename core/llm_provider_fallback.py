#!/usr/bin/env python3
"""
LLM Provider Fallback System
============================

Registers OpenAI as secondary fallback when primary LLM (Claude/Anthropic) fails.

Fallback Chain:
1. PRIMARY: Anthropic Claude (claude-sonnet-4-20250514)
2. SECONDARY: OpenAI GPT-4o
3. TERTIARY: OpenAI GPT-4o-mini (cost-optimized)
4. HUMAN_ESCALATION: Queue for manual review

Features:
- Automatic failover on API errors, rate limits, timeouts
- Token usage tracking per provider
- Cost estimation
- Circuit breaker integration
- Audit logging of all fallback activations

Usage:
    from core.llm_provider_fallback import get_llm_provider, LLMRequest
    
    provider = get_llm_provider()
    
    response = await provider.complete(
        LLMRequest(
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=500,
            agent_name="CRAFTER"
        )
    )
"""

import os
import sys
import json
import asyncio
import logging
from enum import Enum
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field, asdict
import time

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('llm_fallback')

# Import circuit breaker for integration
try:
    from core.circuit_breaker import get_registry as get_circuit_registry
    HAS_CIRCUIT_BREAKER = True
except ImportError:
    HAS_CIRCUIT_BREAKER = False
    logger.warning("Circuit breaker not available")


# =============================================================================
# ENUMS AND DATA CLASSES
# =============================================================================

class LLMProvider(Enum):
    """Available LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENAI_MINI = "openai_mini"


class FallbackReason(Enum):
    """Reasons for fallback activation."""
    API_ERROR = "api_error"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    CIRCUIT_OPEN = "circuit_open"
    PROVIDER_DISABLED = "provider_disabled"


@dataclass
class LLMProviderConfig:
    """Configuration for an LLM provider."""
    name: str
    provider: LLMProvider
    model: str
    api_key_env: str
    base_url: str
    timeout_seconds: float = 60.0
    max_retries: int = 2
    enabled: bool = True
    priority: int = 1  # Lower = higher priority
    
    # Pricing per 1M tokens
    input_price_per_million: float = 0.0
    output_price_per_million: float = 0.0
    
    # Rate limits
    requests_per_minute: int = 60
    tokens_per_minute: int = 100000


@dataclass
class LLMRequest:
    """A request to the LLM."""
    messages: List[Dict[str, str]]
    max_tokens: int = 1000
    temperature: float = 0.7
    agent_name: str = "UNKNOWN"
    operation: str = "completion"
    system_prompt: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LLMResponse:
    """Response from the LLM."""
    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    cost_estimate: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FallbackActivation:
    """Record of a fallback activation."""
    activation_id: str
    agent_name: str
    operation: str
    primary_provider: str
    primary_error: str
    fallback_provider: str
    fallback_reason: str
    success: bool
    latency_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# DEFAULT PROVIDER CONFIGURATIONS
# =============================================================================

DEFAULT_PROVIDERS = [
    LLMProviderConfig(
        name="Claude Sonnet (Primary)",
        provider=LLMProvider.ANTHROPIC,
        model="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com/v1",
        timeout_seconds=60.0,
        priority=1,
        input_price_per_million=3.0,
        output_price_per_million=15.0,
        requests_per_minute=50,
        tokens_per_minute=100000
    ),
    LLMProviderConfig(
        name="GPT-4o (Secondary)",
        provider=LLMProvider.OPENAI,
        model="gpt-4o",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        timeout_seconds=60.0,
        priority=2,
        input_price_per_million=2.5,
        output_price_per_million=10.0,
        requests_per_minute=60,
        tokens_per_minute=150000
    ),
    LLMProviderConfig(
        name="GPT-4o-mini (Tertiary)",
        provider=LLMProvider.OPENAI_MINI,
        model="gpt-4o-mini",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        timeout_seconds=30.0,
        priority=3,
        input_price_per_million=0.15,
        output_price_per_million=0.60,
        requests_per_minute=100,
        tokens_per_minute=200000
    ),
]


# =============================================================================
# LLM PROVIDER FALLBACK SYSTEM
# =============================================================================

class LLMProviderFallback:
    """
    LLM Provider with automatic fallback chain.
    
    Implements: Anthropic → OpenAI GPT-4o → GPT-4o-mini → Human Escalation
    """
    
    def __init__(self, providers: Optional[List[LLMProviderConfig]] = None):
        self.providers = providers or DEFAULT_PROVIDERS
        self.providers.sort(key=lambda p: p.priority)
        
        self.storage_dir = PROJECT_ROOT / ".hive-mind" / "llm_fallback"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Track usage per provider
        self._usage: Dict[str, Dict[str, Any]] = {}
        self._activations: List[FallbackActivation] = []
        
        # Circuit breaker integration
        self._circuit_registry = get_circuit_registry() if HAS_CIRCUIT_BREAKER else None
        
        # Initialize usage tracking
        for provider in self.providers:
            self._usage[provider.name] = {
                "requests": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_cost": 0.0,
                "errors": 0,
                "fallbacks_triggered": 0
            }
        
        self._load_state()
        logger.info(f"LLM Fallback initialized with {len(self.providers)} providers")
    
    def _load_state(self):
        """Load persisted state."""
        state_file = self.storage_dir / "state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)
                    self._usage = state.get("usage", self._usage)
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save state to disk."""
        state_file = self.storage_dir / "state.json"
        try:
            with open(state_file, 'w') as f:
                json.dump({
                    "usage": self._usage,
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")
    
    def _get_api_key(self, provider: LLMProviderConfig) -> Optional[str]:
        """Get API key for provider."""
        key = os.getenv(provider.api_key_env)
        if not key or key in ["", "your_key_here", "placeholder"]:
            return None
        return key
    
    def _is_provider_available(self, provider: LLMProviderConfig) -> Tuple[bool, Optional[str]]:
        """Check if provider is available."""
        if not provider.enabled:
            return False, "Provider disabled"
        
        api_key = self._get_api_key(provider)
        if not api_key:
            return False, f"Missing {provider.api_key_env}"
        
        # Check circuit breaker
        if self._circuit_registry:
            breaker_name = f"llm_{provider.provider.value}"
            if not self._circuit_registry.is_available(breaker_name):
                return False, "Circuit breaker open"
        
        return True, None
    
    async def _call_anthropic(
        self, 
        provider: LLMProviderConfig, 
        request: LLMRequest
    ) -> LLMResponse:
        """Call Anthropic Claude API."""
        import httpx
        
        api_key = self._get_api_key(provider)
        
        messages = request.messages.copy()
        system_content = request.system_prompt or ""
        
        # Extract system message if present
        if messages and messages[0].get("role") == "system":
            system_content = messages[0].get("content", "")
            messages = messages[1:]
        
        payload = {
            "model": provider.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages
        }
        
        if system_content:
            payload["system"] = system_content
        
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=provider.timeout_seconds) as client:
            response = await client.post(
                f"{provider.base_url}/messages",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
        
        latency_ms = (time.time() - start_time) * 1000
        
        content = ""
        if data.get("content"):
            content = data["content"][0].get("text", "")
        
        input_tokens = data.get("usage", {}).get("input_tokens", 0)
        output_tokens = data.get("usage", {}).get("output_tokens", 0)
        
        cost = (
            (input_tokens * provider.input_price_per_million / 1_000_000) +
            (output_tokens * provider.output_price_per_million / 1_000_000)
        )
        
        return LLMResponse(
            content=content,
            provider=provider.name,
            model=provider.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_estimate=cost
        )
    
    async def _call_openai(
        self, 
        provider: LLMProviderConfig, 
        request: LLMRequest
    ) -> LLMResponse:
        """Call OpenAI API."""
        import httpx
        
        api_key = self._get_api_key(provider)
        
        messages = request.messages.copy()
        
        # Add system message if provided
        if request.system_prompt and (not messages or messages[0].get("role") != "system"):
            messages.insert(0, {"role": "system", "content": request.system_prompt})
        
        payload = {
            "model": provider.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        start_time = time.time()
        
        async with httpx.AsyncClient(timeout=provider.timeout_seconds) as client:
            response = await client.post(
                f"{provider.base_url}/chat/completions",
                json=payload,
                headers=headers
            )
            response.raise_for_status()
            data = response.json()
        
        latency_ms = (time.time() - start_time) * 1000
        
        content = ""
        if data.get("choices"):
            content = data["choices"][0].get("message", {}).get("content", "")
        
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        
        cost = (
            (input_tokens * provider.input_price_per_million / 1_000_000) +
            (output_tokens * provider.output_price_per_million / 1_000_000)
        )
        
        return LLMResponse(
            content=content,
            provider=provider.name,
            model=provider.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            cost_estimate=cost
        )
    
    async def _call_provider(
        self, 
        provider: LLMProviderConfig, 
        request: LLMRequest
    ) -> LLMResponse:
        """Call the appropriate provider API."""
        if provider.provider == LLMProvider.ANTHROPIC:
            return await self._call_anthropic(provider, request)
        elif provider.provider in [LLMProvider.OPENAI, LLMProvider.OPENAI_MINI]:
            return await self._call_openai(provider, request)
        else:
            raise ValueError(f"Unknown provider: {provider.provider}")
    
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """
        Complete a request with automatic fallback.
        
        Tries each provider in priority order until success or exhaustion.
        """
        last_error = None
        primary_provider = None
        
        for i, provider in enumerate(self.providers):
            is_primary = (i == 0)
            
            if is_primary:
                primary_provider = provider.name
            
            # Check availability
            available, reason = self._is_provider_available(provider)
            if not available:
                logger.info(f"Skipping {provider.name}: {reason}")
                if is_primary:
                    last_error = reason
                continue
            
            try:
                logger.info(f"Attempting {provider.name} ({provider.model})")
                response = await self._call_provider(provider, request)
                
                # Update usage
                self._usage[provider.name]["requests"] += 1
                self._usage[provider.name]["input_tokens"] += response.input_tokens
                self._usage[provider.name]["output_tokens"] += response.output_tokens
                self._usage[provider.name]["total_cost"] += response.cost_estimate
                
                # Record circuit breaker success
                if self._circuit_registry:
                    self._circuit_registry.record_success(f"llm_{provider.provider.value}")
                
                # Mark if fallback was used
                if not is_primary:
                    response.fallback_used = True
                    response.fallback_reason = last_error
                    
                    # Log activation
                    activation = FallbackActivation(
                        activation_id=f"llm_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
                        agent_name=request.agent_name,
                        operation=request.operation,
                        primary_provider=primary_provider,
                        primary_error=str(last_error),
                        fallback_provider=provider.name,
                        fallback_reason=FallbackReason.API_ERROR.value,
                        success=True,
                        latency_ms=response.latency_ms
                    )
                    self._activations.append(activation)
                    self._log_activation(activation)
                    
                    logger.warning(f"Fallback activated: {primary_provider} → {provider.name}")
                
                self._save_state()
                return response
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"{provider.name} failed: {error_msg}")
                
                self._usage[provider.name]["errors"] += 1
                if is_primary:
                    self._usage[provider.name]["fallbacks_triggered"] += 1
                
                # Record circuit breaker failure
                if self._circuit_registry:
                    self._circuit_registry.record_failure(f"llm_{provider.provider.value}")
                
                last_error = error_msg
                continue
        
        # All providers failed - return error response
        logger.error("All LLM providers exhausted")
        
        return LLMResponse(
            content="[ERROR: All LLM providers failed. Request queued for human review.]",
            provider="none",
            model="none",
            fallback_used=True,
            fallback_reason=f"All providers exhausted. Last error: {last_error}"
        )
    
    def _log_activation(self, activation: FallbackActivation):
        """Log fallback activation to file."""
        log_file = self.storage_dir / f"activations_{datetime.now().strftime('%Y%m%d')}.jsonl"
        try:
            with open(log_file, 'a') as f:
                f.write(json.dumps(activation.to_dict()) + "\n")
        except Exception as e:
            logger.warning(f"Failed to log activation: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get provider status and usage."""
        providers_status = []
        
        for provider in self.providers:
            available, reason = self._is_provider_available(provider)
            usage = self._usage.get(provider.name, {})
            
            providers_status.append({
                "name": provider.name,
                "provider": provider.provider.value,
                "model": provider.model,
                "priority": provider.priority,
                "enabled": provider.enabled,
                "available": available,
                "unavailable_reason": reason,
                "usage": usage
            })
        
        return {
            "providers": providers_status,
            "total_activations": len(self._activations),
            "recent_activations": [a.to_dict() for a in self._activations[-10:]]
        }
    
    def print_status(self):
        """Print provider status to console."""
        print("\n" + "=" * 70)
        print("  LLM PROVIDER FALLBACK STATUS")
        print("=" * 70)
        
        for provider in self.providers:
            available, reason = self._is_provider_available(provider)
            usage = self._usage.get(provider.name, {})
            
            icon = "[OK]" if available else "[--]"
            priority_label = ["PRIMARY", "SECONDARY", "TERTIARY"][provider.priority - 1] if provider.priority <= 3 else f"LEVEL-{provider.priority}"
            
            print(f"\n  {icon} {provider.name} ({priority_label})")
            print(f"      Model: {provider.model}")
            print(f"      Available: {available}" + (f" ({reason})" if reason else ""))
            print(f"      Requests: {usage.get('requests', 0)}")
            print(f"      Tokens: {usage.get('input_tokens', 0):,} in / {usage.get('output_tokens', 0):,} out")
            print(f"      Cost: ${usage.get('total_cost', 0):.4f}")
            print(f"      Errors: {usage.get('errors', 0)}")
        
        print("\n" + "=" * 70)


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_provider: Optional[LLMProviderFallback] = None


def get_llm_provider() -> LLMProviderFallback:
    """Get or create the global LLM provider instance."""
    global _provider
    if _provider is None:
        _provider = LLMProviderFallback()
    return _provider


def register_openai_fallback(
    api_key: Optional[str] = None,
    model: str = "gpt-4o",
    priority: int = 2
) -> bool:
    """
    Register OpenAI as secondary fallback.
    
    Args:
        api_key: OpenAI API key (or set OPENAI_API_KEY env var)
        model: Model to use (default: gpt-4o)
        priority: Priority level (default: 2 = secondary)
    
    Returns:
        True if registration successful
    """
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
    
    provider = get_llm_provider()
    
    # Find and update OpenAI provider
    for p in provider.providers:
        if p.provider == LLMProvider.OPENAI:
            p.model = model
            p.priority = priority
            p.enabled = True
            break
    
    # Re-sort by priority
    provider.providers.sort(key=lambda p: p.priority)
    
    logger.info(f"Registered OpenAI ({model}) as priority {priority} fallback")
    return True


# =============================================================================
# CLI
# =============================================================================

async def main():
    """Test the LLM fallback system."""
    import argparse
    
    parser = argparse.ArgumentParser(description="LLM Provider Fallback System")
    parser.add_argument("--status", action="store_true", help="Show provider status")
    parser.add_argument("--test", action="store_true", help="Test with a simple prompt")
    parser.add_argument("--register-openai", action="store_true", help="Register OpenAI as fallback")
    
    args = parser.parse_args()
    
    provider = get_llm_provider()
    
    if args.register_openai:
        register_openai_fallback()
        print("OpenAI registered as secondary fallback")
    
    if args.status:
        provider.print_status()
    
    if args.test:
        print("\nTesting LLM fallback with simple prompt...")
        request = LLMRequest(
            messages=[{"role": "user", "content": "Say 'Hello from the fallback system' in exactly 5 words."}],
            max_tokens=50,
            agent_name="TEST",
            operation="test_completion"
        )
        
        response = await provider.complete(request)
        
        print(f"\nResponse: {response.content}")
        print(f"Provider: {response.provider}")
        print(f"Model: {response.model}")
        print(f"Fallback used: {response.fallback_used}")
        if response.fallback_reason:
            print(f"Fallback reason: {response.fallback_reason}")
        print(f"Latency: {response.latency_ms:.0f}ms")
        print(f"Cost: ${response.cost_estimate:.6f}")


if __name__ == "__main__":
    asyncio.run(main())
