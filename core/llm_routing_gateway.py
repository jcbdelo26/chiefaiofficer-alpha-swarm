#!/usr/bin/env python3
"""
LLM Routing Gateway
====================
Task-aware multi-provider LLM routing for cost optimization.

Routes different task types to optimal LLM providers:
- GEMINI: Creative work (brand assets, scheduling, creative config)
- CODEX: Hard coding, API connections, code execution
- CLAUDE: Planning, orchestration, self-annealing (the "brain")

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                     LLM ROUTING GATEWAY                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐        │
│  │   CLAUDE       │  │   GEMINI       │  │   CODEX        │        │
│  │  (Brain/Plan)  │  │  (Creative)    │  │  (Code)        │        │
│  │  Opus/Sonnet   │  │  2.5 Flash     │  │  GPT-4/Codex   │        │
│  └────────────────┘  └────────────────┘  └────────────────┘        │
│                              ↑                                       │
│                    ┌─────────────────────┐                          │
│                    │   TASK ROUTER       │                          │
│                    │  (TaskType → LLM)   │                          │
│                    └─────────────────────┘                          │
└─────────────────────────────────────────────────────────────────────┘

Usage:
    from core.llm_routing_gateway import get_llm_router, TaskType
    
    router = get_llm_router()
    
    # Creative task → routes to Gemini
    response = await router.complete(
        messages=[{"role": "user", "content": "Create brand messaging"}],
        task_type=TaskType.CREATIVE,
        agent_name="CRAFTER"
    )
    
    # Coding task → routes to Codex
    response = await router.complete(
        messages=[{"role": "user", "content": "Write API integration code"}],
        task_type=TaskType.CODING,
        agent_name="OPERATOR"
    )
    
    # Planning task → routes to Claude
    response = await router.complete(
        messages=[{"role": "user", "content": "Plan campaign strategy"}],
        task_type=TaskType.PLANNING,
        agent_name="QUEEN"
    )
"""

import os
import sys
import json
import asyncio
import logging
import time
import httpx
from enum import Enum
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple, Union
from dataclasses import dataclass, field, asdict
from abc import ABC, abstractmethod

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('llm_router')

try:
    from core.circuit_breaker import get_registry as get_circuit_registry
    HAS_CIRCUIT_BREAKER = True
except ImportError:
    HAS_CIRCUIT_BREAKER = False
    logger.warning("Circuit breaker not available")


class TaskType(Enum):
    """Task types that determine LLM routing."""
    # Claude tasks (Brain/Orchestration)
    PLANNING = "planning"
    ORCHESTRATION = "orchestration"
    SELF_ANNEALING = "self_annealing"
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    DECISION = "decision"
    STRATEGY = "strategy"
    
    # Gemini tasks (Creative)
    CREATIVE = "creative"
    BRAND_ASSETS = "brand_assets"
    SCHEDULING = "scheduling"
    CONTENT_GENERATION = "content_generation"
    PERSONALIZATION = "personalization"
    MESSAGING = "messaging"
    TEMPLATE_CREATION = "template_creation"
    
    # Codex tasks (Coding)
    CODING = "coding"
    API_INTEGRATION = "api_integration"
    CODE_EXECUTION = "code_execution"
    SCRIPT_GENERATION = "script_generation"
    DATA_TRANSFORMATION = "data_transformation"
    DEBUGGING = "debugging"
    
    # General (uses default routing based on agent)
    GENERAL = "general"


class LLMProviderType(Enum):
    """Available LLM providers."""
    CLAUDE_OPUS = "claude_opus"
    CLAUDE_SONNET = "claude_sonnet"
    GEMINI_FLASH = "gemini_flash"
    GEMINI_PRO = "gemini_pro"
    OPENAI_GPT4 = "openai_gpt4"
    OPENAI_CODEX = "openai_codex"
    OPENAI_O1 = "openai_o1"


# Task type to provider routing table
TASK_ROUTING: Dict[TaskType, List[LLMProviderType]] = {
    # Claude for brain work (primary: Sonnet for speed, Opus fallback for complex)
    TaskType.PLANNING: [LLMProviderType.CLAUDE_SONNET, LLMProviderType.CLAUDE_OPUS],
    TaskType.ORCHESTRATION: [LLMProviderType.CLAUDE_SONNET, LLMProviderType.CLAUDE_OPUS],
    TaskType.SELF_ANNEALING: [LLMProviderType.CLAUDE_SONNET, LLMProviderType.CLAUDE_OPUS],
    TaskType.REASONING: [LLMProviderType.CLAUDE_OPUS, LLMProviderType.OPENAI_O1],
    TaskType.ANALYSIS: [LLMProviderType.CLAUDE_SONNET, LLMProviderType.GEMINI_PRO],
    TaskType.DECISION: [LLMProviderType.CLAUDE_OPUS, LLMProviderType.CLAUDE_SONNET],
    TaskType.STRATEGY: [LLMProviderType.CLAUDE_OPUS, LLMProviderType.CLAUDE_SONNET],
    
    # Gemini for creative work (Flash for speed, Pro for quality)
    TaskType.CREATIVE: [LLMProviderType.GEMINI_FLASH, LLMProviderType.GEMINI_PRO],
    TaskType.BRAND_ASSETS: [LLMProviderType.GEMINI_PRO, LLMProviderType.GEMINI_FLASH],
    TaskType.SCHEDULING: [LLMProviderType.GEMINI_FLASH, LLMProviderType.CLAUDE_SONNET],
    TaskType.CONTENT_GENERATION: [LLMProviderType.GEMINI_FLASH, LLMProviderType.GEMINI_PRO],
    TaskType.PERSONALIZATION: [LLMProviderType.GEMINI_FLASH, LLMProviderType.CLAUDE_SONNET],
    TaskType.MESSAGING: [LLMProviderType.GEMINI_FLASH, LLMProviderType.GEMINI_PRO],
    TaskType.TEMPLATE_CREATION: [LLMProviderType.GEMINI_FLASH, LLMProviderType.GEMINI_PRO],
    
    # OpenAI/Codex for coding work
    TaskType.CODING: [LLMProviderType.OPENAI_GPT4, LLMProviderType.OPENAI_CODEX],
    TaskType.API_INTEGRATION: [LLMProviderType.OPENAI_GPT4, LLMProviderType.CLAUDE_SONNET],
    TaskType.CODE_EXECUTION: [LLMProviderType.OPENAI_CODEX, LLMProviderType.OPENAI_GPT4],
    TaskType.SCRIPT_GENERATION: [LLMProviderType.OPENAI_GPT4, LLMProviderType.OPENAI_CODEX],
    TaskType.DATA_TRANSFORMATION: [LLMProviderType.OPENAI_GPT4, LLMProviderType.GEMINI_FLASH],
    TaskType.DEBUGGING: [LLMProviderType.OPENAI_GPT4, LLMProviderType.CLAUDE_SONNET],
    
    # General defaults to Claude Sonnet
    TaskType.GENERAL: [LLMProviderType.CLAUDE_SONNET, LLMProviderType.OPENAI_GPT4],
}

# Agent to default task type mapping
AGENT_DEFAULT_TASKS: Dict[str, TaskType] = {
    # Brain agents → Claude
    "QUEEN": TaskType.ORCHESTRATION,
    "UNIFIED_QUEEN": TaskType.ORCHESTRATION,
    "ALPHA_QUEEN": TaskType.ORCHESTRATION,
    "GATEKEEPER": TaskType.DECISION,
    "RESEARCHER": TaskType.ANALYSIS,
    
    # Creative agents → Gemini
    "CRAFTER": TaskType.CREATIVE,
    "COACH": TaskType.MESSAGING,
    "SCHEDULER": TaskType.SCHEDULING,
    
    # Pipeline/Coding agents → Codex/GPT-4
    "OPERATOR": TaskType.API_INTEGRATION,
    "HUNTER": TaskType.DATA_TRANSFORMATION,
    "ENRICHER": TaskType.DATA_TRANSFORMATION,
    "SCOUT": TaskType.ANALYSIS,
    "PIPER": TaskType.DATA_TRANSFORMATION,
    
    # Analysis agents → Claude
    "SEGMENTOR": TaskType.ANALYSIS,
}


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""
    provider_type: LLMProviderType
    model: str
    api_key_env: str
    base_url: str
    timeout_seconds: float = 60.0
    max_retries: int = 2
    enabled: bool = True
    
    # Pricing per 1M tokens (for cost tracking)
    input_price_per_million: float = 0.0
    output_price_per_million: float = 0.0
    
    # Rate limits
    requests_per_minute: int = 60
    tokens_per_minute: int = 100000


@dataclass
class RoutedRequest:
    """A request with routing metadata."""
    messages: List[Dict[str, str]]
    task_type: TaskType
    agent_name: str
    max_tokens: int = 2000
    temperature: float = 0.7
    system_prompt: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages": self.messages,
            "task_type": self.task_type.value,
            "agent_name": self.agent_name,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system_prompt": self.system_prompt,
            "metadata": self.metadata
        }


@dataclass
class RoutedResponse:
    """Response with routing and cost metadata."""
    content: str
    provider: str
    model: str
    task_type: str
    agent_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cost_estimate: float = 0.0
    fallback_used: bool = False
    fallback_chain: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Provider configurations
PROVIDER_CONFIGS: Dict[LLMProviderType, ProviderConfig] = {
    LLMProviderType.CLAUDE_OPUS: ProviderConfig(
        provider_type=LLMProviderType.CLAUDE_OPUS,
        model="claude-opus-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com/v1",
        timeout_seconds=120.0,
        input_price_per_million=15.0,
        output_price_per_million=75.0,
        requests_per_minute=30,
        tokens_per_minute=80000
    ),
    LLMProviderType.CLAUDE_SONNET: ProviderConfig(
        provider_type=LLMProviderType.CLAUDE_SONNET,
        model="claude-sonnet-4-20250514",
        api_key_env="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com/v1",
        timeout_seconds=60.0,
        input_price_per_million=3.0,
        output_price_per_million=15.0,
        requests_per_minute=50,
        tokens_per_minute=100000
    ),
    LLMProviderType.GEMINI_FLASH: ProviderConfig(
        provider_type=LLMProviderType.GEMINI_FLASH,
        model="gemini-2.5-flash-preview-05-20",
        api_key_env="GOOGLE_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds=30.0,
        input_price_per_million=0.075,
        output_price_per_million=0.30,
        requests_per_minute=100,
        tokens_per_minute=200000
    ),
    LLMProviderType.GEMINI_PRO: ProviderConfig(
        provider_type=LLMProviderType.GEMINI_PRO,
        model="gemini-2.5-pro-preview-05-06",
        api_key_env="GOOGLE_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds=60.0,
        input_price_per_million=1.25,
        output_price_per_million=10.0,
        requests_per_minute=60,
        tokens_per_minute=150000
    ),
    LLMProviderType.OPENAI_GPT4: ProviderConfig(
        provider_type=LLMProviderType.OPENAI_GPT4,
        model="gpt-4o",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        timeout_seconds=60.0,
        input_price_per_million=2.5,
        output_price_per_million=10.0,
        requests_per_minute=60,
        tokens_per_minute=150000
    ),
    LLMProviderType.OPENAI_CODEX: ProviderConfig(
        provider_type=LLMProviderType.OPENAI_CODEX,
        model="gpt-4o",  # Codex deprecated, use GPT-4o with code prompting
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        timeout_seconds=60.0,
        input_price_per_million=2.5,
        output_price_per_million=10.0,
        requests_per_minute=60,
        tokens_per_minute=150000
    ),
    LLMProviderType.OPENAI_O1: ProviderConfig(
        provider_type=LLMProviderType.OPENAI_O1,
        model="o1",
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        timeout_seconds=180.0,
        input_price_per_million=15.0,
        output_price_per_million=60.0,
        requests_per_minute=20,
        tokens_per_minute=50000
    ),
}


class LLMAdapter(ABC):
    """Abstract base class for LLM provider adapters."""
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.api_key = os.getenv(config.api_key_env)
        self._request_count = 0
        self._total_tokens = 0
        self._total_cost = 0.0
        self._errors = 0
    
    @property
    def is_available(self) -> bool:
        return bool(self.api_key) and self.config.enabled
    
    @abstractmethod
    async def complete(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str] = None
    ) -> Tuple[str, int, int]:
        """Return (content, input_tokens, output_tokens)."""
        pass
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        input_cost = (input_tokens / 1_000_000) * self.config.input_price_per_million
        output_cost = (output_tokens / 1_000_000) * self.config.output_price_per_million
        return input_cost + output_cost
    
    def record_usage(self, input_tokens: int, output_tokens: int, success: bool):
        self._request_count += 1
        self._total_tokens += input_tokens + output_tokens
        if success:
            self._total_cost += self.calculate_cost(input_tokens, output_tokens)
        else:
            self._errors += 1
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "provider": self.config.provider_type.value,
            "model": self.config.model,
            "available": self.is_available,
            "requests": self._request_count,
            "total_tokens": self._total_tokens,
            "total_cost": round(self._total_cost, 4),
            "errors": self._errors
        }


class ClaudeAdapter(LLMAdapter):
    """Adapter for Anthropic Claude models."""
    
    async def complete(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str] = None
    ) -> Tuple[str, int, int]:
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            
            payload = {
                "model": self.config.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            response = await client.post(
                f"{self.config.base_url}/messages",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            content = data["content"][0]["text"] if data.get("content") else ""
            input_tokens = data.get("usage", {}).get("input_tokens", 0)
            output_tokens = data.get("usage", {}).get("output_tokens", 0)
            
            return content, input_tokens, output_tokens


class GeminiAdapter(LLMAdapter):
    """Adapter for Google Gemini models."""
    
    async def complete(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str] = None
    ) -> Tuple[str, int, int]:
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            # Convert messages to Gemini format
            contents = []
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": msg["content"]}]
                })
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": temperature
                }
            }
            
            if system_prompt:
                payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
            
            url = f"{self.config.base_url}/models/{self.config.model}:generateContent?key={self.api_key}"
            
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            content = ""
            if data.get("candidates"):
                parts = data["candidates"][0].get("content", {}).get("parts", [])
                content = parts[0].get("text", "") if parts else ""
            
            usage = data.get("usageMetadata", {})
            input_tokens = usage.get("promptTokenCount", 0)
            output_tokens = usage.get("candidatesTokenCount", 0)
            
            return content, input_tokens, output_tokens


class OpenAIAdapter(LLMAdapter):
    """Adapter for OpenAI models."""
    
    async def complete(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str] = None
    ) -> Tuple[str, int, int]:
        async with httpx.AsyncClient(timeout=self.config.timeout_seconds) as client:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            formatted_messages = []
            if system_prompt:
                formatted_messages.append({"role": "system", "content": system_prompt})
            formatted_messages.extend(messages)
            
            payload = {
                "model": self.config.model,
                "messages": formatted_messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            response = await client.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            
            content = data["choices"][0]["message"]["content"] if data.get("choices") else ""
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            
            return content, input_tokens, output_tokens


class LLMRoutingGateway:
    """
    Task-aware LLM routing gateway.
    
    Routes requests to optimal providers based on task type:
    - Claude for planning/orchestration/reasoning
    - Gemini for creative/content/scheduling
    - OpenAI/Codex for coding/API/execution
    """
    
    def __init__(self):
        self.storage_dir = PROJECT_ROOT / ".hive-mind" / "llm_routing"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self._adapters: Dict[LLMProviderType, LLMAdapter] = {}
        self._circuit_registry = get_circuit_registry() if HAS_CIRCUIT_BREAKER else None
        
        # Usage tracking
        self._usage_by_task: Dict[str, Dict[str, Any]] = {}
        self._usage_by_agent: Dict[str, Dict[str, Any]] = {}
        self._routing_log: List[Dict[str, Any]] = []
        
        self._init_adapters()
        self._load_state()
        
        logger.info(f"LLM Routing Gateway initialized with {len(self._get_available_providers())} providers")
    
    def _init_adapters(self):
        """Initialize all provider adapters."""
        for provider_type, config in PROVIDER_CONFIGS.items():
            if provider_type in [LLMProviderType.CLAUDE_OPUS, LLMProviderType.CLAUDE_SONNET]:
                self._adapters[provider_type] = ClaudeAdapter(config)
            elif provider_type in [LLMProviderType.GEMINI_FLASH, LLMProviderType.GEMINI_PRO]:
                self._adapters[provider_type] = GeminiAdapter(config)
            else:
                self._adapters[provider_type] = OpenAIAdapter(config)
    
    def _get_available_providers(self) -> List[LLMProviderType]:
        """Get list of available providers."""
        return [p for p, a in self._adapters.items() if a.is_available]
    
    def _get_route(self, task_type: TaskType, agent_name: str) -> List[LLMProviderType]:
        """Get the routing chain for a task type."""
        # Get task-specific route
        route = TASK_ROUTING.get(task_type, TASK_ROUTING[TaskType.GENERAL])
        
        # Filter to only available providers
        available = self._get_available_providers()
        route = [p for p in route if p in available]
        
        # If no providers available in route, fallback to any available
        if not route:
            route = available[:2] if available else []
        
        return route
    
    def infer_task_type(self, agent_name: str, messages: List[Dict[str, str]]) -> TaskType:
        """Infer task type from agent name and message content."""
        # Check agent default first
        if agent_name in AGENT_DEFAULT_TASKS:
            return AGENT_DEFAULT_TASKS[agent_name]
        
        # Keyword-based inference from last message
        if messages:
            content = messages[-1].get("content", "").lower()
            
            # Creative keywords
            if any(k in content for k in ["create brand", "messaging", "content", "personalize", "template", "creative"]):
                return TaskType.CREATIVE
            
            # Coding keywords
            if any(k in content for k in ["write code", "api", "function", "script", "debug", "implement"]):
                return TaskType.CODING
            
            # Planning keywords
            if any(k in content for k in ["plan", "strategy", "orchestrate", "decide", "analyze"]):
                return TaskType.PLANNING
        
        return TaskType.GENERAL
    
    async def complete(
        self,
        messages: List[Dict[str, str]],
        task_type: Optional[TaskType] = None,
        agent_name: str = "UNKNOWN",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> RoutedResponse:
        """
        Complete a request with task-aware routing.
        
        Args:
            messages: Chat messages
            task_type: Explicit task type (or inferred from agent/content)
            agent_name: Name of the requesting agent
            max_tokens: Maximum response tokens
            temperature: Sampling temperature
            system_prompt: Optional system prompt
            metadata: Optional metadata for tracking
        
        Returns:
            RoutedResponse with content and routing metadata
        """
        start_time = time.time()
        
        # Infer task type if not provided
        if task_type is None:
            task_type = self.infer_task_type(agent_name, messages)
        
        # Get routing chain
        route = self._get_route(task_type, agent_name)
        
        if not route:
            return RoutedResponse(
                content="[ERROR: No LLM providers available]",
                provider="none",
                model="none",
                task_type=task_type.value,
                agent_name=agent_name,
                fallback_used=False
            )
        
        fallback_chain = []
        last_error = None
        
        for i, provider_type in enumerate(route):
            adapter = self._adapters.get(provider_type)
            if not adapter or not adapter.is_available:
                continue
            
            try:
                logger.info(f"[{agent_name}] {task_type.value} → {provider_type.value}")
                
                content, input_tokens, output_tokens = await adapter.complete(
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system_prompt=system_prompt
                )
                
                adapter.record_usage(input_tokens, output_tokens, success=True)
                
                if self._circuit_registry:
                    self._circuit_registry.record_success(f"llm_{provider_type.value}")
                
                latency_ms = (time.time() - start_time) * 1000
                cost = adapter.calculate_cost(input_tokens, output_tokens)
                
                # Track usage
                self._track_usage(task_type, agent_name, provider_type, input_tokens, output_tokens, cost)
                
                response = RoutedResponse(
                    content=content,
                    provider=provider_type.value,
                    model=adapter.config.model,
                    task_type=task_type.value,
                    agent_name=agent_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    cost_estimate=cost,
                    fallback_used=(i > 0),
                    fallback_chain=fallback_chain
                )
                
                self._log_routing(response, metadata)
                return response
                
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"{provider_type.value} failed: {error_msg}")
                
                adapter.record_usage(0, 0, success=False)
                fallback_chain.append(f"{provider_type.value}:{error_msg[:50]}")
                last_error = error_msg
                
                if self._circuit_registry:
                    self._circuit_registry.record_failure(f"llm_{provider_type.value}")
        
        # All providers failed
        return RoutedResponse(
            content=f"[ERROR: All providers failed. Last error: {last_error}]",
            provider="none",
            model="none",
            task_type=task_type.value,
            agent_name=agent_name,
            fallback_used=True,
            fallback_chain=fallback_chain,
            latency_ms=(time.time() - start_time) * 1000
        )
    
    def _track_usage(
        self,
        task_type: TaskType,
        agent_name: str,
        provider: LLMProviderType,
        input_tokens: int,
        output_tokens: int,
        cost: float
    ):
        """Track usage by task type and agent."""
        # By task type
        if task_type.value not in self._usage_by_task:
            self._usage_by_task[task_type.value] = {
                "requests": 0, "tokens": 0, "cost": 0.0, "providers": {}
            }
        self._usage_by_task[task_type.value]["requests"] += 1
        self._usage_by_task[task_type.value]["tokens"] += input_tokens + output_tokens
        self._usage_by_task[task_type.value]["cost"] += cost
        
        provider_key = provider.value
        if provider_key not in self._usage_by_task[task_type.value]["providers"]:
            self._usage_by_task[task_type.value]["providers"][provider_key] = 0
        self._usage_by_task[task_type.value]["providers"][provider_key] += 1
        
        # By agent
        if agent_name not in self._usage_by_agent:
            self._usage_by_agent[agent_name] = {
                "requests": 0, "tokens": 0, "cost": 0.0, "task_types": {}
            }
        self._usage_by_agent[agent_name]["requests"] += 1
        self._usage_by_agent[agent_name]["tokens"] += input_tokens + output_tokens
        self._usage_by_agent[agent_name]["cost"] += cost
        
        if task_type.value not in self._usage_by_agent[agent_name]["task_types"]:
            self._usage_by_agent[agent_name]["task_types"][task_type.value] = 0
        self._usage_by_agent[agent_name]["task_types"][task_type.value] += 1
    
    def _log_routing(self, response: RoutedResponse, metadata: Optional[Dict[str, Any]]):
        """Log routing decision for analysis."""
        entry = {
            "timestamp": response.timestamp,
            "agent": response.agent_name,
            "task_type": response.task_type,
            "provider": response.provider,
            "model": response.model,
            "tokens": response.input_tokens + response.output_tokens,
            "cost": response.cost_estimate,
            "latency_ms": response.latency_ms,
            "fallback_used": response.fallback_used,
            "metadata": metadata
        }
        self._routing_log.append(entry)
        self._routing_log = self._routing_log[-1000:]  # Keep last 1000
        
        # Auto-save periodically
        if len(self._routing_log) % 50 == 0:
            self._save_state()
    
    def get_status(self) -> Dict[str, Any]:
        """Get gateway status and statistics."""
        providers_status = {}
        for provider_type, adapter in self._adapters.items():
            providers_status[provider_type.value] = adapter.get_stats()
        
        total_cost = sum(s.get("total_cost", 0) for s in providers_status.values())
        total_requests = sum(s.get("requests", 0) for s in providers_status.values())
        
        return {
            "providers": providers_status,
            "usage_by_task": self._usage_by_task,
            "usage_by_agent": self._usage_by_agent,
            "routing_summary": {
                "total_requests": total_requests,
                "total_cost": round(total_cost, 4),
                "recent_routes": len(self._routing_log)
            },
            "task_routing_table": {
                k.value: [p.value for p in v] 
                for k, v in TASK_ROUTING.items()
            },
            "agent_defaults": {
                k: v.value for k, v in AGENT_DEFAULT_TASKS.items()
            }
        }
    
    def get_cost_report(self) -> Dict[str, Any]:
        """Get cost breakdown report."""
        by_provider = {}
        for provider_type, adapter in self._adapters.items():
            stats = adapter.get_stats()
            if stats["requests"] > 0:
                by_provider[provider_type.value] = {
                    "requests": stats["requests"],
                    "tokens": stats["total_tokens"],
                    "cost": stats["total_cost"]
                }
        
        return {
            "by_provider": by_provider,
            "by_task_type": self._usage_by_task,
            "by_agent": self._usage_by_agent,
            "total_cost": sum(p["cost"] for p in by_provider.values()),
            "cost_saved_estimate": self._estimate_savings()
        }
    
    def _estimate_savings(self) -> float:
        """Estimate cost savings from intelligent routing."""
        # Calculate what it would cost if everything used Claude Opus
        total_tokens = sum(
            a.get_stats()["total_tokens"] 
            for a in self._adapters.values()
        )
        opus_config = PROVIDER_CONFIGS[LLMProviderType.CLAUDE_OPUS]
        
        # Assume 30% input, 70% output ratio
        opus_cost = (total_tokens * 0.3 / 1_000_000) * opus_config.input_price_per_million
        opus_cost += (total_tokens * 0.7 / 1_000_000) * opus_config.output_price_per_million
        
        actual_cost = sum(
            a.get_stats()["total_cost"] 
            for a in self._adapters.values()
        )
        
        return round(opus_cost - actual_cost, 4)
    
    def _save_state(self):
        """Save gateway state."""
        state = {
            "usage_by_task": self._usage_by_task,
            "usage_by_agent": self._usage_by_agent,
            "routing_log": self._routing_log[-100:],
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        state_file = self.storage_dir / "routing_state.json"
        try:
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")
    
    def _load_state(self):
        """Load gateway state."""
        state_file = self.storage_dir / "routing_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    state = json.load(f)
                self._usage_by_task = state.get("usage_by_task", {})
                self._usage_by_agent = state.get("usage_by_agent", {})
                self._routing_log = state.get("routing_log", [])
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
    
    def print_status(self):
        """Print status to console."""
        print("\n" + "=" * 70)
        print("  LLM ROUTING GATEWAY STATUS")
        print("=" * 70)
        
        print("\n[Providers]")
        for provider_type, adapter in self._adapters.items():
            stats = adapter.get_stats()
            icon = "✅" if stats["available"] else "❌"
            print(f"  {icon} {provider_type.value}: {stats['model']}")
            print(f"      Requests: {stats['requests']} | Cost: ${stats['total_cost']:.4f}")
        
        print("\n[Task Routing]")
        for task_type in [TaskType.PLANNING, TaskType.CREATIVE, TaskType.CODING]:
            route = TASK_ROUTING.get(task_type, [])
            route_str = " → ".join(p.value for p in route[:2])
            print(f"  {task_type.value}: {route_str}")
        
        print("\n[Cost Summary]")
        report = self.get_cost_report()
        print(f"  Total Cost: ${report['total_cost']:.4f}")
        print(f"  Est. Savings: ${report['cost_saved_estimate']:.4f}")
        
        print("\n" + "=" * 70)


# Singleton instance
_router: Optional[LLMRoutingGateway] = None


def get_llm_router() -> LLMRoutingGateway:
    """Get or create the global LLM routing gateway."""
    global _router
    if _router is None:
        _router = LLMRoutingGateway()
    return _router


async def demo():
    """Demonstrate LLM routing gateway."""
    print("\n" + "=" * 60)
    print("LLM ROUTING GATEWAY - Demo")
    print("=" * 60)
    
    router = get_llm_router()
    
    # Show status
    router.print_status()
    
    # Test routing decisions (without actual API calls)
    print("\n[Routing Decisions (simulated)]")
    
    test_cases = [
        ("QUEEN", TaskType.ORCHESTRATION, "Plan the next campaign phase"),
        ("CRAFTER", TaskType.CREATIVE, "Create personalized email content"),
        ("OPERATOR", TaskType.CODING, "Write API integration code"),
        ("SEGMENTOR", TaskType.ANALYSIS, "Analyze lead scoring patterns"),
        ("SCHEDULER", TaskType.SCHEDULING, "Find optimal meeting times"),
    ]
    
    for agent, task_type, prompt in test_cases:
        route = router._get_route(task_type, agent)
        route_str = " → ".join(p.value for p in route[:2]) if route else "NO ROUTE"
        print(f"  {agent} ({task_type.value}): {route_str}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
