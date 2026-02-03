# ============================================================================
# WEEK 1, CHUNK 1: Merge Revenue Swarm into Alpha Swarm
# ============================================================================
# 
# Source: D:\Agent Swarm Orchestration\revenue-swarm
# Target: D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm
#
# This script:
# 1. Copies execution scripts with 'revenue_' prefix
# 2. Copies .claude agents and commands
# 3. Merges .hive-mind directories
# 4. Updates imports in copied files
# ============================================================================

param(
    [switch]$DryRun = $false,
    [switch]$Force = $false
)

$ErrorActionPreference = "Stop"

# Configuration
$sourceDir = "D:\Agent Swarm Orchestration\revenue-swarm"
$targetDir = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$logFile = "$targetDir\scripts\merge_log_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"

# Logging function
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logMessage = "[$timestamp] [$Level] $Message"
    Write-Host $logMessage -ForegroundColor $(
        switch ($Level) {
            "INFO" { "White" }
            "SUCCESS" { "Green" }
            "WARNING" { "Yellow" }
            "ERROR" { "Red" }
            default { "White" }
        }
    )
    if (-not $DryRun) {
        Add-Content -Path $logFile -Value $logMessage
    }
}

# ============================================================================
# STEP 1: Validate directories
# ============================================================================
Write-Log "=" * 60
Write-Log "MERGE REVENUE SWARM INTO ALPHA SWARM"
Write-Log "=" * 60
Write-Log "Source: $sourceDir"
Write-Log "Target: $targetDir"
Write-Log "Dry Run: $DryRun"
Write-Log ""

if (-not (Test-Path $sourceDir)) {
    Write-Log "Source directory not found: $sourceDir" "ERROR"
    exit 1
}

if (-not (Test-Path $targetDir)) {
    Write-Log "Target directory not found: $targetDir" "ERROR"
    exit 1
}

# Create log directory
if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path "$targetDir\scripts" | Out-Null
}

# ============================================================================
# STEP 2: Copy execution scripts with 'revenue_' prefix
# ============================================================================
Write-Log ""
Write-Log "STEP 2: Copying execution scripts..." "INFO"

$executionFiles = @(
    @{Source = "queen_digital_mind.py"; Target = "revenue_queen_digital_mind.py"},
    @{Source = "queen_master_orchestrator.py"; Target = "revenue_queen_master_orchestrator.py"},
    @{Source = "scout_intent_detection.py"; Target = "revenue_scout_intent_detection.py"}
)

foreach ($file in $executionFiles) {
    $sourcePath = "$sourceDir\execution\$($file.Source)"
    $targetPath = "$targetDir\execution\$($file.Target)"
    
    if (Test-Path $sourcePath) {
        if ($DryRun) {
            Write-Log "[DRY RUN] Would copy: $($file.Source) → $($file.Target)" "INFO"
        } else {
            # Read content
            $content = Get-Content $sourcePath -Raw
            
            # Update imports to work in new location
            $content = $content -replace 'from execution\.', 'from execution.revenue_'
            $content = $content -replace "from coordination\.", "from revenue_coordination."
            $content = $content -replace '\.hive-mind/', '.hive-mind/'
            
            # Add header comment
            $header = @"
# ============================================================================
# MERGED FROM: revenue-swarm
# ORIGINAL FILE: $($file.Source)
# MERGED DATE: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
# ============================================================================

"@
            $content = $header + $content
            
            # Write to target
            Set-Content -Path $targetPath -Value $content -Encoding UTF8
            Write-Log "Copied: $($file.Source) → $($file.Target)" "SUCCESS"
        }
    } else {
        Write-Log "Source file not found: $sourcePath" "WARNING"
    }
}

# ============================================================================
# STEP 3: Copy .claude agents (selective - revenue-specific)
# ============================================================================
Write-Log ""
Write-Log "STEP 3: Copying .claude agents..." "INFO"

# Create revenue agents directory
$revenueAgentsDir = "$targetDir\.claude\agents\revenue"
if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path $revenueAgentsDir | Out-Null
}

# Copy key agent directories
$agentDirsToCopy = @(
    "hive-mind",
    "goal",
    "reasoning",
    "neural"
)

foreach ($dir in $agentDirsToCopy) {
    $sourcePath = "$sourceDir\.claude\agents\$dir"
    $targetPath = "$revenueAgentsDir\$dir"
    
    if (Test-Path $sourcePath) {
        if ($DryRun) {
            Write-Log "[DRY RUN] Would copy agent dir: $dir" "INFO"
        } else {
            Copy-Item -Path $sourcePath -Destination $targetPath -Recurse -Force
            Write-Log "Copied agents: $dir → revenue\$dir" "SUCCESS"
        }
    }
}

# ============================================================================
# STEP 4: Copy .claude commands (selective - revenue-specific)
# ============================================================================
Write-Log ""
Write-Log "STEP 4: Copying .claude commands..." "INFO"

# Create revenue commands directory
$revenueCommandsDir = "$targetDir\.claude\commands\revenue"
if (-not $DryRun) {
    New-Item -ItemType Directory -Force -Path $revenueCommandsDir | Out-Null
}

# Copy key command directories
$commandDirsToCopy = @(
    "hive-mind",
    "coordination",
    "hooks",
    "memory"
)

foreach ($dir in $commandDirsToCopy) {
    $sourcePath = "$sourceDir\.claude\commands\$dir"
    $targetPath = "$revenueCommandsDir\$dir"
    
    if (Test-Path $sourcePath) {
        if ($DryRun) {
            Write-Log "[DRY RUN] Would copy command dir: $dir" "INFO"
        } else {
            Copy-Item -Path $sourcePath -Destination $targetPath -Recurse -Force
            Write-Log "Copied commands: $dir → revenue\$dir" "SUCCESS"
        }
    }
}

# ============================================================================
# STEP 5: Merge .hive-mind directories
# ============================================================================
Write-Log ""
Write-Log "STEP 5: Merging .hive-mind directories..." "INFO"

# Create new .hive-mind subdirectories for Revenue Swarm
$hiveMindDirs = @(
    "knowledge",      # ChromaDB vector store
    "meetings",       # Meeting transcripts
    "intent_signals", # SCOUT intent detection output
    "reasoning_bank"  # Self-annealing learnings
)

foreach ($dir in $hiveMindDirs) {
    $targetPath = "$targetDir\.hive-mind\$dir"
    if ($DryRun) {
        Write-Log "[DRY RUN] Would create: .hive-mind\$dir" "INFO"
    } else {
        New-Item -ItemType Directory -Force -Path $targetPath | Out-Null
        Write-Log "Created: .hive-mind\$dir" "SUCCESS"
    }
}

# Copy reasoning_bank.json if exists
$reasoningBankSource = "$sourceDir\.hive-mind\reasoning_bank.json"
$reasoningBankTarget = "$targetDir\.hive-mind\reasoning_bank\revenue_reasoning_bank.json"

if (Test-Path $reasoningBankSource) {
    if ($DryRun) {
        Write-Log "[DRY RUN] Would copy: reasoning_bank.json" "INFO"
    } else {
        Copy-Item -Path $reasoningBankSource -Destination $reasoningBankTarget -Force
        Write-Log "Copied: reasoning_bank.json → reasoning_bank\revenue_reasoning_bank.json" "SUCCESS"
    }
}

# ============================================================================
# STEP 6: Copy coordination directory
# ============================================================================
Write-Log ""
Write-Log "STEP 6: Copying coordination directory..." "INFO"

$coordSource = "$sourceDir\coordination"
$coordTarget = "$targetDir\revenue_coordination"

if (Test-Path $coordSource) {
    if ($DryRun) {
        Write-Log "[DRY RUN] Would copy: coordination → revenue_coordination" "INFO"
    } else {
        Copy-Item -Path $coordSource -Destination $coordTarget -Recurse -Force
        Write-Log "Copied: coordination → revenue_coordination" "SUCCESS"
    }
}

# ============================================================================
# STEP 7: Copy key documentation
# ============================================================================
Write-Log ""
Write-Log "STEP 7: Copying key documentation..." "INFO"

$docsToCopy = @(
    "COMPLETE_AGENT_ECOSYSTEM.md",
    "NATIVE_AGENTIC_FUNCTIONS.md",
    "SYSTEM_OVERVIEW.md"
)

foreach ($doc in $docsToCopy) {
    $sourcePath = "$sourceDir\$doc"
    $targetPath = "$targetDir\docs\revenue_swarm\$doc"
    
    if (Test-Path $sourcePath) {
        if ($DryRun) {
            Write-Log "[DRY RUN] Would copy doc: $doc" "INFO"
        } else {
            New-Item -ItemType Directory -Force -Path "$targetDir\docs\revenue_swarm" | Out-Null
            Copy-Item -Path $sourcePath -Destination $targetPath -Force
            Write-Log "Copied doc: $doc → docs\revenue_swarm\$doc" "SUCCESS"
        }
    }
}

# ============================================================================
# STEP 8: Update requirements.txt
# ============================================================================
Write-Log ""
Write-Log "STEP 8: Updating requirements.txt..." "INFO"

$newDependencies = @(
    "exa-py>=1.0.0  # SCOUT intent detection",
    "chromadb>=0.4.0  # QUEEN digital mind",
    "openai-whisper>=20231117  # PIPER transcription (optional)"
)

$reqPath = "$targetDir\requirements.txt"
if (Test-Path $reqPath) {
    $existingReqs = Get-Content $reqPath
    
    foreach ($dep in $newDependencies) {
        $depName = ($dep -split ">=")[0].Trim()
        $alreadyExists = $existingReqs | Where-Object { $_ -match "^$depName" }
        
        if (-not $alreadyExists) {
            if ($DryRun) {
                Write-Log "[DRY RUN] Would add dependency: $depName" "INFO"
            } else {
                Add-Content -Path $reqPath -Value $dep
                Write-Log "Added dependency: $depName" "SUCCESS"
            }
        } else {
            Write-Log "Dependency already exists: $depName" "INFO"
        }
    }
}

# ============================================================================
# STEP 9: Create unified agent registry
# ============================================================================
Write-Log ""
Write-Log "STEP 9: Creating unified agent registry..." "INFO"

$registryContent = @'
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

import os
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
            module_path="execution.enricher_clay_waterfall"
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
            description="Outbound execution (GHL integration)",
            module_path="execution.revenue_operator_outbound",
            status=AgentStatus.NOT_INITIALIZED  # Future implementation
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
            module_path="execution.revenue_coach_self_annealing",
            status=AgentStatus.NOT_INITIALIZED  # Future implementation
        )
    
    def initialize_agent(self, agent_name: str) -> bool:
        """Initialize a specific agent."""
        if agent_name not in self.agents:
            print(f"❌ Unknown agent: {agent_name}")
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
                        print(f"✅ Initialized: {agent.name}")
                        return True
                    except Exception:
                        continue
            
            agent.status = AgentStatus.ERROR
            return False
            
        except ImportError as e:
            print(f"⚠️ Could not import {agent_name}: {e}")
            agent.status = AgentStatus.NOT_INITIALIZED
            return False
        except Exception as e:
            print(f"❌ Error initializing {agent_name}: {e}")
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
                        AgentStatus.AVAILABLE: "✅",
                        AgentStatus.BUSY: "🔄",
                        AgentStatus.ERROR: "❌",
                        AgentStatus.NOT_INITIALIZED: "⬜"
                    }.get(agent.status, "❓")
                    
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
        status = "✅" if success else "⬜"
        print(f"  {status} {name}")
    
    registry.print_status()


if __name__ == "__main__":
    main()
'@

$registryPath = "$targetDir\execution\unified_agent_registry.py"
if ($DryRun) {
    Write-Log "[DRY RUN] Would create: execution\unified_agent_registry.py" "INFO"
} else {
    Set-Content -Path $registryPath -Value $registryContent -Encoding UTF8
    Write-Log "Created: execution\unified_agent_registry.py" "SUCCESS"
}

# ============================================================================
# SUMMARY
# ============================================================================
Write-Log ""
Write-Log "=" * 60
Write-Log "MERGE COMPLETE!" "SUCCESS"
Write-Log "=" * 60
Write-Log ""
Write-Log "Files copied:"
Write-Log "  - execution/revenue_*.py (3 files)"
Write-Log "  - .claude/agents/revenue/* (agent definitions)"
Write-Log "  - .claude/commands/revenue/* (command definitions)"
Write-Log "  - revenue_coordination/ (coordination config)"
Write-Log "  - docs/revenue_swarm/*.md (documentation)"
Write-Log ""
Write-Log "New directories created:"
Write-Log "  - .hive-mind/knowledge/"
Write-Log "  - .hive-mind/meetings/"
Write-Log "  - .hive-mind/intent_signals/"
Write-Log "  - .hive-mind/reasoning_bank/"
Write-Log ""
Write-Log "New files created:"
Write-Log "  - execution/unified_agent_registry.py"
Write-Log ""
Write-Log "Next steps:"
Write-Log "  1. Run: python execution\unified_agent_registry.py"
Write-Log "  2. Test SCOUT: python execution\revenue_scout_intent_detection.py"
Write-Log "  3. Verify imports work correctly"
Write-Log ""

if ($DryRun) {
    Write-Log "This was a DRY RUN. No files were modified." "WARNING"
    Write-Log "Run without -DryRun to perform actual merge." "INFO"
}
