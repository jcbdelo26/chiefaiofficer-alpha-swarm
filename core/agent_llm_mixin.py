#!/usr/bin/env python3
"""
Agent LLM Mixin
===============
Provides LLM routing capabilities to agents with automatic task type inference.

Usage:
    from core.agent_llm_mixin import AgentLLMMixin, TaskType
    
    class CrafterAgent(AgentLLMMixin):
        def __init__(self):
            super().__init__(agent_name="CRAFTER")
        
        async def generate_email(self, lead_data: dict):
            # Automatically routes to Gemini for creative work
            response = await self.llm_complete(
                prompt="Create personalized email for {name}".format(**lead_data),
                task_type=TaskType.CREATIVE
            )
            return response.content
    
    class QueenAgent(AgentLLMMixin):
        def __init__(self):
            super().__init__(agent_name="QUEEN")
        
        async def plan_campaign(self, context: dict):
            # Automatically routes to Claude for planning
            response = await self.llm_complete(
                prompt="Plan campaign strategy",
                task_type=TaskType.PLANNING
            )
            return response.content
"""

from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass

from core.llm_routing_gateway import (
    get_llm_router,
    TaskType,
    LLMProviderType,
    RoutedResponse,
    AGENT_DEFAULT_TASKS
)


class AgentLLMMixin:
    """
    Mixin that provides LLM routing capabilities to agents.
    
    Automatically routes to the optimal LLM provider based on:
    1. Explicit task_type parameter
    2. Agent's default task type
    3. Content-based inference
    """
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self._router = get_llm_router()
        self._default_task_type = AGENT_DEFAULT_TASKS.get(agent_name, TaskType.GENERAL)
    
    async def llm_complete(
        self,
        prompt: str,
        task_type: Optional[TaskType] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        context_messages: Optional[List[Dict[str, str]]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> RoutedResponse:
        """
        Complete an LLM request with automatic routing.
        
        Args:
            prompt: The user prompt
            task_type: Override task type (otherwise uses agent default)
            system_prompt: Optional system prompt
            max_tokens: Maximum response tokens
            temperature: Sampling temperature
            context_messages: Previous conversation context
            metadata: Additional tracking metadata
        
        Returns:
            RoutedResponse with content and metadata
        """
        messages = context_messages or []
        messages.append({"role": "user", "content": prompt})
        
        return await self._router.complete(
            messages=messages,
            task_type=task_type or self._default_task_type,
            agent_name=self.agent_name,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
            metadata=metadata
        )
    
    async def creative_complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.8
    ) -> RoutedResponse:
        """Shortcut for creative tasks (routes to Gemini)."""
        return await self.llm_complete(
            prompt=prompt,
            task_type=TaskType.CREATIVE,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
    
    async def coding_complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.3
    ) -> RoutedResponse:
        """Shortcut for coding tasks (routes to Codex/GPT-4)."""
        code_system = system_prompt or (
            "You are an expert programmer. Write clean, efficient, well-documented code. "
            "Follow best practices and include error handling."
        )
        return await self.llm_complete(
            prompt=prompt,
            task_type=TaskType.CODING,
            system_prompt=code_system,
            max_tokens=max_tokens,
            temperature=temperature
        )
    
    async def planning_complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 3000,
        temperature: float = 0.5
    ) -> RoutedResponse:
        """Shortcut for planning tasks (routes to Claude)."""
        return await self.llm_complete(
            prompt=prompt,
            task_type=TaskType.PLANNING,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
    
    async def analysis_complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.4
    ) -> RoutedResponse:
        """Shortcut for analysis tasks (routes to Claude)."""
        return await self.llm_complete(
            prompt=prompt,
            task_type=TaskType.ANALYSIS,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature
        )
    
    def get_llm_stats(self) -> Dict[str, Any]:
        """Get LLM usage statistics for this agent."""
        status = self._router.get_status()
        return status.get("usage_by_agent", {}).get(self.agent_name, {
            "requests": 0,
            "tokens": 0,
            "cost": 0.0,
            "task_types": {}
        })


# Convenience functions for agents that don't use inheritance

async def llm_complete_for_agent(
    agent_name: str,
    prompt: str,
    task_type: Optional[TaskType] = None,
    system_prompt: Optional[str] = None,
    max_tokens: int = 2000,
    temperature: float = 0.7,
    context_messages: Optional[List[Dict[str, str]]] = None
) -> RoutedResponse:
    """
    Complete an LLM request for a specific agent.
    
    Use this when you can't use the mixin pattern.
    """
    router = get_llm_router()
    
    messages = context_messages or []
    messages.append({"role": "user", "content": prompt})
    
    if task_type is None:
        task_type = AGENT_DEFAULT_TASKS.get(agent_name, TaskType.GENERAL)
    
    return await router.complete(
        messages=messages,
        task_type=task_type,
        agent_name=agent_name,
        max_tokens=max_tokens,
        temperature=temperature,
        system_prompt=system_prompt
    )


# Pre-configured agent helpers

async def queen_think(prompt: str, context: Optional[str] = None) -> RoutedResponse:
    """QUEEN orchestration thinking (routes to Claude Opus)."""
    system = "You are the QUEEN orchestrator of a 12-agent sales swarm. Make strategic decisions."
    if context:
        system += f"\n\nContext:\n{context}"
    return await llm_complete_for_agent(
        "QUEEN", prompt, TaskType.ORCHESTRATION, system_prompt=system
    )


async def crafter_create(prompt: str, lead_context: Optional[Dict] = None) -> RoutedResponse:
    """CRAFTER creative content (routes to Gemini)."""
    system = "You are a master copywriter creating personalized B2B outreach."
    if lead_context:
        system += f"\n\nLead Info: {lead_context}"
    return await llm_complete_for_agent(
        "CRAFTER", prompt, TaskType.CREATIVE, system_prompt=system, temperature=0.8
    )


async def operator_code(prompt: str) -> RoutedResponse:
    """OPERATOR coding tasks (routes to Codex/GPT-4)."""
    system = "You are an expert Python developer building API integrations."
    return await llm_complete_for_agent(
        "OPERATOR", prompt, TaskType.CODING, system_prompt=system, temperature=0.3, max_tokens=4000
    )


async def segmentor_analyze(prompt: str, data_context: Optional[str] = None) -> RoutedResponse:
    """SEGMENTOR analysis (routes to Claude)."""
    system = "You are a data analyst specializing in lead scoring and segmentation."
    if data_context:
        system += f"\n\nData Context:\n{data_context}"
    return await llm_complete_for_agent(
        "SEGMENTOR", prompt, TaskType.ANALYSIS, system_prompt=system, temperature=0.4
    )
