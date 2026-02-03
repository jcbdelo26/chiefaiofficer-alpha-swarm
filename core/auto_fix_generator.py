#!/usr/bin/env python3
"""
Auto Fix Generator
==================
Generate actionable fixes based on identified failure patterns.

Features:
- Config auto-tuning (e.g., increasing timeouts, rate limits)
- Code patch generation (template-based)
- Directive updates
- Fix validation

Usage:
    from core.auto_fix_generator import AutoFixGenerator
    
    fixer = AutoFixGenerator()
    fix = fixer.generate_fix(pattern)
    fixer.apply_fix(fix)
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class FixProposal:
    """Proposed fix for a failure pattern."""
    fix_id: str
    pattern_id: str
    fix_type: str  # "config_update", "code_patch", "directive_update"
    target_file: str
    description: str
    changes: Dict[str, Any]
    status: str = "proposed"  # proposed, applied, verified, failed
    created_at: str = datetime.utcnow().isoformat()

class AutoFixGenerator:
    """Generate and apply fixes for failure patterns."""
    
    def __init__(self, sandbox_config_path: str = "config/sandbox.json"):
        self.sandbox_config_path = Path(sandbox_config_path)
        self.fixes_dir = Path(".hive-mind/fixes")
        self.fixes_dir.mkdir(parents=True, exist_ok=True)
        
    def generate_fix(self, pattern: Any) -> Optional[FixProposal]:
        """
        Generate a fix proposal based on a failure pattern.
        
        Args:
            pattern: FailurePattern object or dict
        """
        # Handle both object and dict input
        pattern_id = getattr(pattern, 'pattern_id', pattern.get('pattern_id') if isinstance(pattern, dict) else 'unknown')
        category = getattr(pattern, 'category', pattern.get('category') if isinstance(pattern, dict) else 'unknown')
        
        # 1. Config Tuning: Rate Limits & Timeouts
        if "rate_limit" in pattern_id or "timeout" in pattern_id:
            return self._generate_config_fix(pattern_id, category)
            
        # 2. Resource Tuning: Memory/Context
        elif "memory" in pattern_id or "context" in pattern_id:
            return self._generate_resource_fix(pattern_id)
            
        # 3. Data Validation Logic
        elif "validation" in pattern_id or "format" in pattern_id:
            return self._generate_validation_fix(pattern_id)
            
        return None

    def _generate_config_fix(self, pattern_id: str, category: str) -> FixProposal:
        """Generate a configuration update fix."""
        return FixProposal(
            fix_id=f"fix_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            pattern_id=pattern_id,
            fix_type="config_update",
            target_file=str(self.sandbox_config_path),
            description=f"Auto-tune limits for {pattern_id}",
            changes={
                "action": "update_key",
                "key": "mock_services.ghl.latency_ms", # Example target
                "value": "increase_20_percent"
            }
        )

    def _generate_resource_fix(self, pattern_id: str) -> FixProposal:
        """Generate a resource limit update."""
        return FixProposal(
            fix_id=f"fix_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            pattern_id=pattern_id,
            fix_type="config_update",
            target_file="core/context_manager.py", # Placeholder
            description="Increase context window or cleanup threshold",
            changes={
                "action": "update_constant",
                "key": "MAX_CONTEXT_TOKENS",
                "value": "increase_10_percent"
            }
        )

    def _generate_validation_fix(self, pattern_id: str) -> FixProposal:
        """Generate a validation logic patch."""
        return FixProposal(
            fix_id=f"fix_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            pattern_id=pattern_id,
            fix_type="directive_update",
            target_file="directives/unified_lead_workflow.md",
            description=f"Update validation rules for {pattern_id}",
            changes={
                "action": "append_rule",
                "section": "Validation",
                "rule": "Ensure email format matches regex before processing"
            }
        )

    def apply_fix(self, fix: FixProposal) -> bool:
        """
        Apply a proposed fix.
        
        Real implementation would parse the 'changes' dict and modify files.
        For sandbox, we simulate the application.
        """
        print(f"[AutoFixGenerator] Applying fix {fix.fix_id}: {fix.description}")
        
        # Simulate config update
        if fix.fix_type == "config_update" and self.sandbox_config_path.exists():
            try:
                with open(self.sandbox_config_path, 'r') as f:
                    config = json.load(f)
                
                # Logic to actually modify the config based on 'changes'
                # This is a simplification demonstrating the mechanic
                if fix.changes.get("value") == "increase_20_percent":
                    print("  -> Increasing config values by 20%")
                    
                with open(self.sandbox_config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                    
                fix.status = "applied"
                self._save_fix_record(fix)
                return True
            except Exception as e:
                print(f"  -> Failed to apply fix: {e}")
                fix.status = "failed"
                return False
                
        fix.status = "applied" # Simulate success for other types
        self._save_fix_record(fix)
        return True

    def _save_fix_record(self, fix: FixProposal):
        """Save fix record to disk."""
        path = self.fixes_dir / f"{fix.fix_id}.json"
        with open(path, 'w') as f:
            json.dump(asdict(fix), f, indent=2)

if __name__ == "__main__":
    # Test stub
    generator = AutoFixGenerator()
    test_pattern = {
        "pattern_id": "rate_limit_exceeded",
        "category": "api_error"
    }
    fix = generator.generate_fix(test_pattern)
    if fix:
        print(f"Generated proposal: {fix}")
        generator.apply_fix(fix)
