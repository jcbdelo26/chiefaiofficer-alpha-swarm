#!/usr/bin/env python3
"""
Unified Agent Registry
======================
Single interface to all agents across Alpha Swarm + Revenue Swarm.

Alpha Swarm Agents:
- HUNTER: LinkedIn scraping
- ENRICHER: Data enrichment (Clay)
- SEGMENTOR: ICP scoring
- CRAFTER: Campaign generation (RPI)
- GATEKEEPER: Human approval

Revenue Swarm Agents:
- QUEEN: Master orchestrator + digital mind
- SCOUT: Intent detection (Exa)
- OPERATOR: Outbound execution (future)
- PIPER: Real-time engagement (future)
- COACH: Self-annealing (future)
"""

import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class AgentSwarm(Enum):
    """Agent swarm origin."""
    ALPHA = "alpha"
    REVENUE = "revenue"


class AgentStatus(Enum):
    """Agent status."""
    AVAILABLE = "available"
    BUSY = "busy"
    ERROR = "error"
    NOT_INITIALIZED = "not_initialized"


@dataclass
class AgentInfo:
    """Agent metadata."""
    name: str
    swarm: AgentSwarm
    description: str
    module_path: str
    status: AgentStatus = AgentStatus.NOT_INITIALIZED
    instance: Any = None


class UnifiedAgentRegistry:
    """
    Registry for all agents across both swarms.
    
    Usage:
        registry = UnifiedAgentRegistry()
        registry.initialize_all()
        
        # Get specific agent
        scout = registry.get_agent("scout")
        signals = scout.detect_intent_signals("Acme Corp")
        
        # Run workflow
        results = registry.run_workflow("lead_to_campaign", linkedin_url="...")
    """
    
    def __init__(self):
        self.agents: Dict[str, AgentInfo] = {}
        self._register_all_agents()
    
    def _register_all_agents(self):
        """Register all known agents."""
        
        # Alpha Swarm agents
        self.agents["hunter"] = AgentInfo(
            name="HUNTER",
            swarm=AgentSwarm.ALPHA,
            description="LinkedIn scraping (followers, events, groups, posts)",
            module_path="execution.hunter_scrape_followers"
        )
        
        self.agents["enricher"] = AgentInfo(
            name="ENRICHER",
            swarm=AgentSwarm.ALPHA,
            description="Data enrichment via Clay waterfall",
            module_path="execution.enricher_waterfall"
        )
        
        self.agents["segmentor"] = AgentInfo(
            name="SEGMENTOR",
            swarm=AgentSwarm.ALPHA,
            description="ICP scoring and lead classification",
            module_path="execution.segmentor_classify"
        )
        
        self.agents["crafter"] = AgentInfo(
            name="CRAFTER",
            swarm=AgentSwarm.ALPHA,
            description="RPI campaign generation",
            module_path="execution.crafter_campaign"
        )
        
        self.agents["gatekeeper"] = AgentInfo(
            name="GATEKEEPER",
            swarm=AgentSwarm.ALPHA,
            description="Human approval queue and dashboard",
            module_path="execution.gatekeeper_queue"
        )
        
        self.agents["responder"] = AgentInfo(
            name="RESPONDER",
            swarm=AgentSwarm.ALPHA,
            description="Objection handling and reply classification",
            module_path="execution.responder_objections"
        )
        
        # Revenue Swarm agents
        self.agents["queen"] = AgentInfo(
            name="QUEEN",
            swarm=AgentSwarm.REVENUE,
            description="Master orchestrator with digital mind (ChromaDB)",
            module_path="execution.revenue_queen_digital_mind"
        )
        
        self.agents["scout"] = AgentInfo(
            name="SCOUT",
            swarm=AgentSwarm.REVENUE,
            description="Intent detection via Exa Search",
            module_path="execution.revenue_scout_intent_detection"
        )
        
        self.agents["operator"] = AgentInfo(
            name="OPERATOR",
            swarm=AgentSwarm.REVENUE,
            description="Unified outbound execution (Instantly email + HeyReach LinkedIn + GHL nurture)",
            module_path="execution.operator_outbound",
            status=AgentStatus.NOT_INITIALIZED
        )
        
        self.agents["piper"] = AgentInfo(
            name="PIPER",
            swarm=AgentSwarm.REVENUE,
            description="Real-time visitor engagement",
            module_path="execution.revenue_piper_visitor_scan",
            status=AgentStatus.NOT_INITIALIZED  # Future implementation
        )
        
        self.agents["coach"] = AgentInfo(
            name="COACH",
            swarm=AgentSwarm.REVENUE,
            description="Self-annealing and performance optimization",
            module_path="core.self_annealing",
            status=AgentStatus.NOT_INITIALIZED
        )
    
    def initialize_agent(self, agent_name: str) -> bool:
        """Initialize a specific agent."""
        if agent_name not in self.agents:
            print(f"âŒ Unknown agent: {agent_name}")
            return False
        
        agent = self.agents[agent_name]
        
        try:
            # Dynamic import
            module_parts = agent.module_path.split(".")
            module = __import__(agent.module_path, fromlist=[module_parts[-1]])
            
            # Find the main class in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and attr_name.lower() != "enum":
                    # Try to instantiate
                    try:
                        agent.instance = attr()
                        agent.status = AgentStatus.AVAILABLE
                        print(f"âœ… Initialized: {agent.name}")
                        return True
                    except Exception:
                        continue
            
            agent.status = AgentStatus.ERROR
            return False
            
        except ImportError as e:
            print(f"âš ï¸ Could not import {agent_name}: {e}")
            agent.status = AgentStatus.NOT_INITIALIZED
            return False
        except Exception as e:
            print(f"âŒ Error initializing {agent_name}: {e}")
            agent.status = AgentStatus.ERROR
            return False
    
    def initialize_all(self, swarm: Optional[AgentSwarm] = None) -> Dict[str, bool]:
        """Initialize all agents (optionally filtered by swarm)."""
        results = {}
        
        for name, agent in self.agents.items():
            if swarm is None or agent.swarm == swarm:
                results[name] = self.initialize_agent(name)
        
        return results
    
    def get_agent(self, agent_name: str) -> Optional[Any]:
        """Get an initialized agent instance."""
        if agent_name not in self.agents:
            return None
        
        agent = self.agents[agent_name]
        
        if agent.status != AgentStatus.AVAILABLE:
            self.initialize_agent(agent_name)
        
        return agent.instance
    
    def list_agents(self, swarm: Optional[AgentSwarm] = None) -> List[AgentInfo]:
        """List all registered agents."""
        agents = list(self.agents.values())
        
        if swarm:
            agents = [a for a in agents if a.swarm == swarm]
        
        return agents
    
    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all agents."""
        return {
            name: {
                "swarm": agent.swarm.value,
                "status": agent.status.value,
                "description": agent.description
            }
            for name, agent in self.agents.items()
        }
    
    def print_status(self):
        """Print agent status table."""
        print("\n" + "=" * 70)
        print("UNIFIED AGENT REGISTRY STATUS")
        print("=" * 70)
        
        for swarm in AgentSwarm:
            print(f"\n{swarm.value.upper()} SWARM:")
            print("-" * 40)
            
            for name, agent in self.agents.items():
                if agent.swarm == swarm:
                    status_icon = {
                        AgentStatus.AVAILABLE: "âœ…",
                        AgentStatus.BUSY: "ðŸ”„",
                        AgentStatus.ERROR: "âŒ",
                        AgentStatus.NOT_INITIALIZED: "â¬œ"
                    }.get(agent.status, "â“")
                    
                    print(f"  {status_icon} {agent.name:12} - {agent.description[:40]}")
        
        print("\n" + "=" * 70)


def main():
    """Test the unified agent registry."""
    print("Testing Unified Agent Registry...")
    
    registry = UnifiedAgentRegistry()
    registry.print_status()
    
    # Try to initialize available agents
    print("\nInitializing agents...")
    results = registry.initialize_all()
    
    for name, success in results.items():
        status = "âœ…" if success else "â¬œ"
        print(f"  {status} {name}")
    
    registry.print_status()


if __name__ == "__main__":
    main()
