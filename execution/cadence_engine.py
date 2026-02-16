#!/usr/bin/env python3
"""
Multi-Channel Cadence Engine
==============================
Manages the 21-day Email + LinkedIn outreach sequence per lead.

Each lead progresses through a defined cadence (sequence of touchpoints).
The engine tracks state, evaluates conditions, and produces "actions due"
for OPERATOR to dispatch.

Cadence flow:
    Day 1:  Email intro
    Day 2:  LinkedIn connection request (if has linkedin_url)
    Day 5:  Email value follow-up (if not replied)
    Day 7:  LinkedIn message (if connected)
    Day 10: Email social proof (if not replied)
    Day 14: LinkedIn follow-up (if connected)
    Day 17: Email break-up (if not replied)
    Day 21: Email graceful close (if not replied)

Exit conditions: replied, meeting_booked, bounced, unsubscribed, linkedin_replied

Usage:
    python execution/cadence_engine.py --due          # Show actions due today
    python execution/cadence_engine.py --status       # Show all cadence states
    python execution/cadence_engine.py --enroll test@example.com --tier tier_1
    python execution/cadence_engine.py --sync         # Sync signal loop exits
"""

import sys
import json
import argparse
import platform
import logging
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict, field

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console

_is_windows = platform.system() == "Windows"
console = Console(force_terminal=not _is_windows)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cadence_engine")


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class CadenceStep:
    """A single step in the cadence sequence."""
    step: int
    day: int
    channel: str        # "email" or "linkedin"
    action: str         # "intro", "connect", "value_followup", etc.
    description: str
    condition: str      # "always", "has_linkedin_url", "not_replied", "linkedin_connected"


@dataclass
class CadenceAction:
    """An action due for dispatch today."""
    email: str
    step: CadenceStep
    cadence_id: str
    tier: str
    linkedin_url: str
    lead_data: Dict[str, Any]


@dataclass
class LeadCadenceState:
    """Per-lead cadence progress tracking."""
    email: str
    cadence_id: str
    tier: str
    started_at: str
    current_step: int           # 1-indexed step number (next to execute)
    status: str                 # "active", "completed", "paused", "exited"
    exit_reason: str = ""
    linkedin_url: str = ""
    linkedin_connected: bool = False
    lead_data: Dict[str, Any] = field(default_factory=dict)
    steps_completed: List[Dict] = field(default_factory=list)
    last_step_at: str = ""
    next_step_due: str = ""     # ISO date
    paused_at: str = ""


# =============================================================================
# CADENCE ENGINE
# =============================================================================

class CadenceEngine:
    """
    Manages multi-channel outreach cadences.

    Reads cadence definitions from production.json.
    Tracks per-lead state in .hive-mind/cadence_state/.
    Produces actions due today for OPERATOR dispatch.
    """

    def __init__(self, hive_dir: Path = None):
        self.hive_dir = hive_dir or (PROJECT_ROOT / ".hive-mind")
        self._config: Dict = {}
        self._cadence_configs: Dict = {}
        self._signal_mgr = None

        self._load_config()

        # State directory
        self.state_dir = self.hive_dir / "cadence_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self):
        config_path = PROJECT_ROOT / "config" / "production.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
        self._cadence_configs = self._config.get("cadence", {})

    def _get_signal_manager(self):
        if self._signal_mgr is None:
            from core.lead_signals import LeadStatusManager
            self._signal_mgr = LeadStatusManager(hive_dir=self.hive_dir)
        return self._signal_mgr

    # -------------------------------------------------------------------------
    # Cadence definition parsing
    # -------------------------------------------------------------------------

    def get_cadence_definition(self, cadence_id: str = "default_21day") -> Tuple[Dict, List[CadenceStep]]:
        """Load cadence definition and parse steps."""
        cadence_cfg = self._cadence_configs.get(cadence_id, {})
        if not cadence_cfg:
            raise ValueError(f"Cadence '{cadence_id}' not found in config")

        steps = []
        for step_cfg in cadence_cfg.get("steps", []):
            steps.append(CadenceStep(
                step=step_cfg["step"],
                day=step_cfg["day"],
                channel=step_cfg["channel"],
                action=step_cfg["action"],
                description=step_cfg.get("description", ""),
                condition=step_cfg.get("condition", "always"),
            ))

        return cadence_cfg, steps

    def get_exit_statuses(self, cadence_id: str = "default_21day") -> List[str]:
        """Get statuses that should exit the cadence."""
        cadence_cfg = self._cadence_configs.get(cadence_id, {})
        return cadence_cfg.get("exit_on", [])

    def get_pause_statuses(self, cadence_id: str = "default_21day") -> List[str]:
        """Get statuses that should pause the cadence."""
        cadence_cfg = self._cadence_configs.get(cadence_id, {})
        return cadence_cfg.get("pause_on", [])

    # -------------------------------------------------------------------------
    # State management
    # -------------------------------------------------------------------------

    def _email_to_filename(self, email: str) -> str:
        return email.lower().replace("@", "_at_").replace(".", "_") + ".json"

    def _load_lead_state(self, email: str) -> Optional[LeadCadenceState]:
        filepath = self.state_dir / self._email_to_filename(email)
        if filepath.exists():
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                return LeadCadenceState(**data)
            except (json.JSONDecodeError, TypeError, OSError):
                return None
        return None

    def _save_lead_state(self, state: LeadCadenceState):
        filepath = self.state_dir / self._email_to_filename(state.email)
        filepath.write_text(json.dumps(asdict(state), indent=2, default=str), encoding="utf-8")

    def get_all_cadence_states(self) -> List[LeadCadenceState]:
        """Load all lead cadence states."""
        states = []
        for filepath in sorted(self.state_dir.glob("*.json")):
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
                states.append(LeadCadenceState(**data))
            except (json.JSONDecodeError, TypeError, OSError):
                continue
        return states

    # -------------------------------------------------------------------------
    # Enrollment
    # -------------------------------------------------------------------------

    def enroll(
        self,
        email: str,
        tier: str = "tier_2",
        cadence_id: str = "default_21day",
        linkedin_url: str = "",
        lead_data: Optional[Dict] = None,
    ) -> LeadCadenceState:
        """
        Enroll a lead into a cadence sequence.

        Idempotent: if already enrolled and active, returns existing state.
        """
        existing = self._load_lead_state(email)
        if existing and existing.status == "active":
            logger.info("Lead %s already active in cadence %s (step %d)",
                        email, existing.cadence_id, existing.current_step)
            return existing

        now = datetime.now(timezone.utc)
        # Day 1 action is due immediately (today)
        next_due = now.date().isoformat()

        state = LeadCadenceState(
            email=email,
            cadence_id=cadence_id,
            tier=tier,
            started_at=now.isoformat(),
            current_step=1,
            status="active",
            linkedin_url=linkedin_url,
            linkedin_connected=False,
            lead_data=lead_data or {},
            steps_completed=[],
            last_step_at="",
            next_step_due=next_due,
        )

        self._save_lead_state(state)
        logger.info("Enrolled %s in cadence %s (tier=%s)", email, cadence_id, tier)
        return state

    # -------------------------------------------------------------------------
    # Due actions (the core scheduler)
    # -------------------------------------------------------------------------

    def get_due_actions(self, cadence_id: str = "default_21day") -> List[CadenceAction]:
        """
        Scan all active leads and return actions due today.

        For each active lead:
        1. Check if next_step_due <= today
        2. Evaluate the step's condition
        3. If condition met, add to actions list
        4. If condition not met (e.g., linkedin_connected but not connected),
           skip to next step that's due
        """
        today = date.today()
        cadence_cfg, steps = self.get_cadence_definition(cadence_id)
        exit_statuses = self.get_exit_statuses(cadence_id)

        actions: List[CadenceAction] = []
        states = self.get_all_cadence_states()

        for state in states:
            if state.status != "active":
                continue
            if state.cadence_id != cadence_id:
                continue

            # Check if due
            try:
                due_date = date.fromisoformat(state.next_step_due)
            except (ValueError, TypeError):
                continue

            if due_date > today:
                continue  # Not yet due

            # Check signal loop for exits
            if self._should_exit(state.email, exit_statuses):
                continue  # Will be handled by sync_signals()

            # Find current step definition
            current_step_def = None
            for s in steps:
                if s.step == state.current_step:
                    current_step_def = s
                    break

            if not current_step_def:
                # Past last step — cadence complete
                continue

            # Evaluate condition
            if self._evaluate_condition(current_step_def.condition, state):
                actions.append(CadenceAction(
                    email=state.email,
                    step=current_step_def,
                    cadence_id=cadence_id,
                    tier=state.tier,
                    linkedin_url=state.linkedin_url,
                    lead_data=state.lead_data,
                ))
            else:
                # Condition not met — skip this step, advance to next
                self._advance_to_next_step(state, steps, skip_reason=current_step_def.condition)

        return actions

    def _evaluate_condition(self, condition: str, state: LeadCadenceState) -> bool:
        """Evaluate whether a cadence step's condition is met."""
        if condition == "always":
            return True

        if condition == "has_linkedin_url":
            return bool(state.linkedin_url)

        if condition == "not_replied":
            # Check signal loop for reply
            mgr = self._get_signal_manager()
            lead_status = mgr.get_lead_status(state.email)
            if lead_status:
                status = lead_status.get("status", "")
                if status in ("replied", "linkedin_replied", "meeting_booked"):
                    return False
            return True

        if condition == "linkedin_connected":
            # Check actual LinkedIn connection status from signal loop
            if state.linkedin_connected:
                return True
            # Also check signal loop
            mgr = self._get_signal_manager()
            lead_status = mgr.get_lead_status(state.email)
            if lead_status and lead_status.get("linkedin_status") == "connected":
                # Update cached state
                state.linkedin_connected = True
                self._save_lead_state(state)
                return True
            return False

        logger.warning("Unknown cadence condition: %s", condition)
        return True

    def _advance_to_next_step(
        self,
        state: LeadCadenceState,
        steps: List[CadenceStep],
        skip_reason: str = "",
    ):
        """Advance lead to the next cadence step (skipping current)."""
        # Find next step
        next_steps = [s for s in steps if s.step > state.current_step]
        if not next_steps:
            # Cadence complete
            state.status = "completed"
            state.exit_reason = "all_steps_done"
            self._save_lead_state(state)
            logger.info("Cadence complete for %s (all steps done)", state.email)
            return

        next_step = next_steps[0]
        start_date = date.fromisoformat(state.started_at[:10])
        next_due = start_date + timedelta(days=next_step.day - 1)

        state.current_step = next_step.step
        state.next_step_due = next_due.isoformat()
        state.steps_completed.append({
            "step": state.current_step - 1,
            "action": "skipped",
            "reason": f"condition_not_met:{skip_reason}",
            "at": datetime.now(timezone.utc).isoformat(),
        })

        self._save_lead_state(state)
        logger.info("Skipped step for %s (condition: %s), next step %d on %s",
                     state.email, skip_reason, next_step.step, next_due)

    # -------------------------------------------------------------------------
    # Step completion (called by OPERATOR after dispatch)
    # -------------------------------------------------------------------------

    def mark_step_done(
        self,
        email: str,
        step_num: int,
        result: str = "dispatched",
        metadata: Optional[Dict] = None,
    ):
        """Record a completed step and advance to next."""
        state = self._load_lead_state(email)
        if not state or state.status != "active":
            return

        _, steps = self.get_cadence_definition(state.cadence_id)
        now = datetime.now(timezone.utc)

        state.steps_completed.append({
            "step": step_num,
            "action": result,
            "at": now.isoformat(),
            **({"metadata": metadata} if metadata else {}),
        })
        state.last_step_at = now.isoformat()

        # Find next step
        next_steps = [s for s in steps if s.step > step_num]
        if not next_steps:
            state.status = "completed"
            state.exit_reason = "all_steps_done"
            logger.info("Cadence complete for %s after step %d", email, step_num)
        else:
            next_step = next_steps[0]
            start_date = date.fromisoformat(state.started_at[:10])
            next_due = start_date + timedelta(days=next_step.day - 1)
            state.current_step = next_step.step
            state.next_step_due = next_due.isoformat()
            logger.info("Lead %s advanced to step %d (due %s)",
                        email, next_step.step, next_due)

        self._save_lead_state(state)

    # -------------------------------------------------------------------------
    # Signal loop sync (auto-exit on reply/bounce/unsub)
    # -------------------------------------------------------------------------

    def sync_signals(self, cadence_id: str = "default_21day") -> Dict[str, List[str]]:
        """
        Sync cadence states with signal loop.

        Checks all active leads for exit/pause conditions based on
        their current engagement status from LeadStatusManager.

        Returns dict of {"exited": [...], "paused": [...]}.
        """
        exit_statuses = self.get_exit_statuses(cadence_id)
        pause_statuses = self.get_pause_statuses(cadence_id)

        result = {"exited": [], "paused": [], "connected": []}
        states = self.get_all_cadence_states()
        mgr = self._get_signal_manager()

        for state in states:
            if state.status not in ("active", "paused"):
                continue
            if state.cadence_id != cadence_id:
                continue

            lead_status = mgr.get_lead_status(state.email)
            if not lead_status:
                continue

            current_status = lead_status.get("status", "")

            # Check for exit
            if current_status in exit_statuses:
                state.status = "exited"
                state.exit_reason = current_status
                self._save_lead_state(state)
                result["exited"].append(state.email)
                logger.info("Cadence exit: %s (reason: %s)", state.email, current_status)
                continue

            # Check for pause
            if state.status == "active" and current_status in pause_statuses:
                state.status = "paused"
                state.paused_at = datetime.now(timezone.utc).isoformat()
                self._save_lead_state(state)
                result["paused"].append(state.email)
                logger.info("Cadence paused: %s (reason: %s)", state.email, current_status)
                continue

            # Check for LinkedIn connection (update cached flag)
            if lead_status.get("linkedin_status") == "connected" and not state.linkedin_connected:
                state.linkedin_connected = True
                self._save_lead_state(state)
                result["connected"].append(state.email)

        logger.info("Signal sync: %d exited, %d paused, %d connected",
                     len(result["exited"]), len(result["paused"]), len(result["connected"]))
        return result

    def _should_exit(self, email: str, exit_statuses: List[str]) -> bool:
        """Quick check if lead should exit cadence."""
        mgr = self._get_signal_manager()
        lead_status = mgr.get_lead_status(email)
        if not lead_status:
            return False
        return lead_status.get("status", "") in exit_statuses

    # -------------------------------------------------------------------------
    # Manual controls
    # -------------------------------------------------------------------------

    def pause_lead(self, email: str, reason: str = "manual"):
        """Manually pause a lead's cadence."""
        state = self._load_lead_state(email)
        if state and state.status == "active":
            state.status = "paused"
            state.paused_at = datetime.now(timezone.utc).isoformat()
            state.exit_reason = f"paused:{reason}"
            self._save_lead_state(state)
            logger.info("Cadence paused for %s (reason: %s)", email, reason)

    def resume_lead(self, email: str):
        """Resume a paused cadence."""
        state = self._load_lead_state(email)
        if state and state.status == "paused":
            state.status = "active"
            state.paused_at = ""
            state.exit_reason = ""
            self._save_lead_state(state)
            logger.info("Cadence resumed for %s", email)

    def exit_lead(self, email: str, reason: str = "manual"):
        """Manually exit a lead from cadence."""
        state = self._load_lead_state(email)
        if state and state.status in ("active", "paused"):
            state.status = "exited"
            state.exit_reason = reason
            self._save_lead_state(state)
            logger.info("Cadence exited for %s (reason: %s)", email, reason)

    # -------------------------------------------------------------------------
    # Status / dashboard
    # -------------------------------------------------------------------------

    def get_cadence_summary(self) -> Dict[str, Any]:
        """Aggregate cadence stats for dashboard display."""
        states = self.get_all_cadence_states()

        by_status = {"active": 0, "completed": 0, "paused": 0, "exited": 0}
        by_step = {}
        exit_reasons = {}

        for s in states:
            by_status[s.status] = by_status.get(s.status, 0) + 1

            if s.status == "active":
                step_key = f"step_{s.current_step}"
                by_step[step_key] = by_step.get(step_key, 0) + 1

            if s.exit_reason:
                exit_reasons[s.exit_reason] = exit_reasons.get(s.exit_reason, 0) + 1

        due_today = len(self.get_due_actions())

        return {
            "total_enrolled": len(states),
            "by_status": by_status,
            "by_current_step": by_step,
            "exit_reasons": exit_reasons,
            "actions_due_today": due_today,
        }


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Multi-Channel Cadence Engine")
    parser.add_argument("--due", action="store_true", help="Show actions due today")
    parser.add_argument("--status", action="store_true", help="Show cadence summary")
    parser.add_argument("--list", action="store_true", help="List all cadence states")
    parser.add_argument("--enroll", type=str, help="Enroll a lead (email)")
    parser.add_argument("--tier", type=str, default="tier_2", help="ICP tier for enrollment")
    parser.add_argument("--linkedin-url", type=str, default="", help="LinkedIn URL for enrollment")
    parser.add_argument("--sync", action="store_true", help="Sync signal loop exits")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    engine = CadenceEngine()

    if args.enroll:
        state = engine.enroll(args.enroll, tier=args.tier, linkedin_url=args.linkedin_url)
        if args.json:
            print(json.dumps(asdict(state), indent=2, default=str))
        else:
            console.print(f"[green]Enrolled[/green] {state.email} in {state.cadence_id} "
                          f"(tier={state.tier}, step={state.current_step})")
        return

    if args.sync:
        result = engine.sync_signals()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            console.print(f"[bold]Signal Sync[/bold]")
            console.print(f"  Exited:    {len(result['exited'])}")
            console.print(f"  Paused:    {len(result['paused'])}")
            console.print(f"  Connected: {len(result['connected'])}")
            for email in result["exited"]:
                console.print(f"    [red]EXIT[/red] {email}")
            for email in result["paused"]:
                console.print(f"    [yellow]PAUSE[/yellow] {email}")
        return

    if args.due:
        actions = engine.get_due_actions()
        if args.json:
            print(json.dumps([{
                "email": a.email,
                "step": a.step.step,
                "day": a.step.day,
                "channel": a.step.channel,
                "action": a.step.action,
                "description": a.step.description,
                "tier": a.tier,
            } for a in actions], indent=2))
        else:
            console.print(f"\n[bold]Cadence Actions Due Today[/bold] ({len(actions)} actions)\n")
            if not actions:
                console.print("[dim]No actions due today.[/dim]")
                return
            for a in actions:
                color = "cyan" if a.step.channel == "email" else "blue"
                console.print(
                    f"  Step {a.step.step} (Day {a.step.day}) "
                    f"[{color}]{a.step.channel}[/{color}] → {a.email} "
                    f"| {a.step.description} | tier={a.tier}"
                )
        return

    if args.list:
        states = engine.get_all_cadence_states()
        if args.json:
            print(json.dumps([asdict(s) for s in states], indent=2, default=str))
        else:
            console.print(f"\n[bold]All Cadence States[/bold] ({len(states)} leads)\n")
            for s in states:
                color = "green" if s.status == "active" else "yellow" if s.status == "paused" else "dim"
                console.print(
                    f"  [{color}]{s.status:10}[/{color}] {s.email} "
                    f"step={s.current_step} due={s.next_step_due} "
                    f"tier={s.tier} linkedin={'Y' if s.linkedin_connected else 'N'}"
                )
                if s.exit_reason:
                    console.print(f"             exit: {s.exit_reason}")
        return

    if args.status:
        summary = engine.get_cadence_summary()
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            console.print(f"\n[bold]Cadence Summary[/bold]")
            console.print(f"  Total enrolled: {summary['total_enrolled']}")
            console.print(f"  Active:         {summary['by_status'].get('active', 0)}")
            console.print(f"  Completed:      {summary['by_status'].get('completed', 0)}")
            console.print(f"  Paused:         {summary['by_status'].get('paused', 0)}")
            console.print(f"  Exited:         {summary['by_status'].get('exited', 0)}")
            console.print(f"  Due today:      {summary['actions_due_today']}")
            if summary["exit_reasons"]:
                console.print(f"\n  Exit reasons:")
                for reason, count in summary["exit_reasons"].items():
                    console.print(f"    {reason}: {count}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
