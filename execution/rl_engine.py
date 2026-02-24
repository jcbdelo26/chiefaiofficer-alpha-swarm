#!/usr/bin/env python3
"""
Reinforcement Learning Engine
=============================
Adaptive decision-making using Q-learning for campaign optimization.

Learns optimal:
- Template selection
- Send timing
- Personalization depth
- Channel selection

Usage:
    from execution.rl_engine import RLEngine
    
    engine = RLEngine()
    action = engine.select_action(state)
    engine.update(state, action, reward, next_state)
"""

import os
import sys
import json
import random
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

console = Console()


def _utc_now() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass
class RLState:
    """Represents a state in the RL environment."""
    icp_tier: str
    intent_bucket: str
    source_type: str
    day_of_week: int
    time_bucket: str
    
    def to_key(self) -> str:
        return f"{self.icp_tier}|{self.intent_bucket}|{self.source_type}|{self.day_of_week}|{self.time_bucket}"


@dataclass
class Experience:
    """Single experience tuple for replay."""
    state: str
    action: str
    reward: float
    next_state: str
    timestamp: str


class RLEngine:
    """
    Reinforcement Learning engine using Q-learning.
    
    Optimizes decisions across multiple dimensions:
    - Template selection (which email template)
    - Timing (when to send)
    - Personalization (how much to customize)
    - Channel (email, LinkedIn, multi-channel)
    """
    
    # Available actions
    TEMPLATE_ACTIONS = [
        "template_competitor_displacement",
        "template_event_followup",
        "template_thought_leadership",
        "template_community_outreach",
        "template_website_visitor"
    ]
    
    TIMING_ACTIONS = [
        "timing_immediate",
        "timing_morning_optimal",
        "timing_afternoon_optimal",
        "timing_next_business_day"
    ]
    
    PERSONALIZATION_ACTIONS = [
        "personalization_high",
        "personalization_medium",
        "personalization_low"
    ]
    
    CHANNEL_ACTIONS = [
        "channel_email_only",
        "channel_linkedin_only",
        "channel_multi_touch"
    ]
    
    # Reward signals
    REWARD_SIGNALS = {
        "email_opened": 1.0,
        "email_clicked": 3.0,
        "reply_received": 10.0,
        "positive_reply": 20.0,
        "meeting_booked": 50.0,
        "deal_closed": 100.0,
        "unsubscribe": -10.0,
        "spam_report": -50.0,
        "bounce": -5.0,
        "no_response": -1.0
    }
    
    def __init__(self,
                 learning_rate: float = 0.1,
                 discount_factor: float = 0.95,
                 epsilon: float = 0.1,
                 epsilon_decay: float = 0.995,
                 min_epsilon: float = 0.01):
        
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.min_epsilon = min_epsilon
        
        # Q-table: state -> action -> Q-value
        self.q_table: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        
        # Experience replay buffer
        self.experience_buffer: List[Experience] = []
        self.max_buffer_size = 10000
        
        # Episode tracking
        self.episode_rewards: List[float] = []
        self.current_episode_reward = 0.0
        
        # Action counts for exploration metrics
        self.action_counts: Dict[str, int] = defaultdict(int)
        
        # Load existing policy if available
        self._load_policy()
    
    def get_state(self, lead: Dict[str, Any], context: Dict[str, Any] = None) -> RLState:
        """
        Encode lead and context into an RL state.
        """
        context = context or {}
        
        # ICP tier
        icp_tier = lead.get("icp_tier", "tier_4")
        
        # Intent bucket
        intent_score = lead.get("intent_score", 0)
        if intent_score >= 80:
            intent_bucket = "hot"
        elif intent_score >= 50:
            intent_bucket = "warm"
        else:
            intent_bucket = "cold"
        
        # Source type (simplified)
        source_type = lead.get("source_type", "unknown")
        source_map = {
            "competitor_follower": "competitor",
            "event_attendee": "event",
            "group_member": "community",
            "post_commenter": "engaged",
            "post_liker": "passive",
            "website_visitor": "visitor"
        }
        source_type = source_map.get(source_type, "unknown")
        
        # Time context
        now = _utc_now()
        day_of_week = now.weekday()
        hour = now.hour
        
        if 9 <= hour < 12:
            time_bucket = "morning"
        elif 12 <= hour < 14:
            time_bucket = "lunch"
        elif 14 <= hour < 17:
            time_bucket = "afternoon"
        elif 17 <= hour < 20:
            time_bucket = "evening"
        else:
            time_bucket = "off_hours"
        
        return RLState(
            icp_tier=icp_tier,
            intent_bucket=intent_bucket,
            source_type=source_type,
            day_of_week=day_of_week,
            time_bucket=time_bucket
        )
    
    def get_all_actions(self, action_type: str = None) -> List[str]:
        """Get available actions, optionally filtered by type."""
        
        if action_type == "template":
            return self.TEMPLATE_ACTIONS
        elif action_type == "timing":
            return self.TIMING_ACTIONS
        elif action_type == "personalization":
            return self.PERSONALIZATION_ACTIONS
        elif action_type == "channel":
            return self.CHANNEL_ACTIONS
        else:
            # All actions
            return (self.TEMPLATE_ACTIONS + self.TIMING_ACTIONS + 
                    self.PERSONALIZATION_ACTIONS + self.CHANNEL_ACTIONS)
    
    def select_action(self, state: RLState, action_type: str = None) -> str:
        """
        Select action using epsilon-greedy strategy.
        
        With probability epsilon: explore (random action)
        With probability 1-epsilon: exploit (best known action)
        """
        
        state_key = state.to_key()
        actions = self.get_all_actions(action_type)
        
        if random.random() < self.epsilon:
            # Explore: random action
            action = random.choice(actions)
        else:
            # Exploit: best known action
            action = self._get_best_action(state_key, actions)
        
        self.action_counts[action] += 1
        return action
    
    def _get_best_action(self, state_key: str, actions: List[str]) -> str:
        """Get the best action for a state based on Q-values."""
        
        if state_key not in self.q_table:
            # No experience, return first action
            return actions[0]
        
        state_q = self.q_table[state_key]
        
        # Get action with highest Q-value
        best_action = None
        best_value = float('-inf')
        
        for action in actions:
            value = state_q.get(action, 0.0)
            if value > best_value:
                best_value = value
                best_action = action
        
        return best_action or actions[0]
    
    def calculate_reward(self, outcome: Dict[str, Any]) -> float:
        """
        Calculate reward from campaign outcome.
        
        Outcome dict should contain counts of various signals.
        """
        
        reward = 0.0
        
        for signal, weight in self.REWARD_SIGNALS.items():
            count = outcome.get(signal, 0)
            reward += count * weight
        
        return reward
    
    def update(self, state: RLState, action: str, reward: float, next_state: RLState):
        """
        Update Q-value using Q-learning update rule.
        
        Q(s, a) = Q(s, a) + α * (r + γ * max(Q(s', a')) - Q(s, a))
        """
        
        state_key = state.to_key()
        next_state_key = next_state.to_key()
        
        # Get current Q-value
        current_q = self.q_table[state_key][action]
        
        # Get max Q-value for next state
        if next_state_key in self.q_table:
            max_next_q = max(self.q_table[next_state_key].values()) if self.q_table[next_state_key] else 0.0
        else:
            max_next_q = 0.0
        
        # Q-learning update
        new_q = current_q + self.learning_rate * (
            reward + self.discount_factor * max_next_q - current_q
        )
        
        self.q_table[state_key][action] = new_q
        
        # Track episode reward
        self.current_episode_reward += reward
        
        # Store experience
        self._store_experience(state_key, action, reward, next_state_key)
        
        # Decay epsilon
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)
    
    def _store_experience(self, state: str, action: str, reward: float, next_state: str):
        """Store experience in replay buffer."""
        
        experience = Experience(
            state=state,
            action=action,
            reward=reward,
            next_state=next_state,
            timestamp=_utc_now().isoformat()
        )
        
        self.experience_buffer.append(experience)
        
        # Trim buffer if too large
        if len(self.experience_buffer) > self.max_buffer_size:
            self.experience_buffer = self.experience_buffer[-self.max_buffer_size:]
    
    def end_episode(self):
        """End current episode and record reward."""
        
        self.episode_rewards.append(self.current_episode_reward)
        self.current_episode_reward = 0.0
    
    def replay_batch(self, batch_size: int = 32):
        """
        Experience replay: learn from random batch of past experiences.
        Helps stabilize learning.
        """
        
        if len(self.experience_buffer) < batch_size:
            return
        
        batch = random.sample(self.experience_buffer, batch_size)
        
        for exp in batch:
            # Get current Q-value
            current_q = self.q_table[exp.state][exp.action]
            
            # Get max Q-value for next state
            if exp.next_state in self.q_table:
                max_next_q = max(self.q_table[exp.next_state].values()) if self.q_table[exp.next_state] else 0.0
            else:
                max_next_q = 0.0
            
            # Update
            new_q = current_q + self.learning_rate * (
                exp.reward + self.discount_factor * max_next_q - current_q
            )
            
            self.q_table[exp.state][exp.action] = new_q
    
    def get_policy_summary(self, top_n: int = 10) -> Dict[str, Any]:
        """Get summary of learned policy."""
        
        # Find states with most experience
        state_action_counts = []
        for state, actions in self.q_table.items():
            for action, q_value in actions.items():
                state_action_counts.append({
                    "state": state,
                    "action": action,
                    "q_value": q_value
                })
        
        # Sort by Q-value
        state_action_counts.sort(key=lambda x: x["q_value"], reverse=True)
        
        return {
            "total_states": len(self.q_table),
            "total_experiences": len(self.experience_buffer),
            "avg_episode_reward": sum(self.episode_rewards[-100:]) / max(1, len(self.episode_rewards[-100:])),
            "current_epsilon": self.epsilon,
            "top_actions": state_action_counts[:top_n],
            "action_distribution": dict(self.action_counts)
        }
    
    def save_policy(self, path: Path = None):
        """Save learned policy to disk."""
        
        if path is None:
            path = Path(__file__).parent.parent / ".hive-mind" / "rl_policy.json"
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert defaultdict to regular dict
        q_table_serializable = {
            state: dict(actions)
            for state, actions in self.q_table.items()
        }
        
        policy_data = {
            "q_table": q_table_serializable,
            "episode_rewards": self.episode_rewards[-1000:],
            "action_counts": dict(self.action_counts),
            "epsilon": self.epsilon,
            "saved_at": _utc_now().isoformat(),
            "version": "1.0.0"
        }
        
        with open(path, "w") as f:
            json.dump(policy_data, f, indent=2)
        
        console.print(f"[green]Saved RL policy to {path}[/green]")
    
    def _load_policy(self):
        """Load policy from disk if available."""
        
        path = Path(__file__).parent.parent / ".hive-mind" / "rl_policy.json"
        
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                
                # Restore Q-table
                for state, actions in data.get("q_table", {}).items():
                    for action, value in actions.items():
                        self.q_table[state][action] = value
                
                self.episode_rewards = data.get("episode_rewards", [])
                self.action_counts = defaultdict(int, data.get("action_counts", {}))
                self.epsilon = data.get("epsilon", self.epsilon)
                
                console.print(f"[dim]Loaded RL policy with {len(self.q_table)} states[/dim]")
                
            except Exception as e:
                console.print(f"[yellow]Failed to load RL policy: {e}[/yellow]")
    
    def print_policy_table(self):
        """Print nicely formatted policy summary."""
        
        summary = self.get_policy_summary()
        
        table = Table(title="RL Policy Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total States", str(summary["total_states"]))
        table.add_row("Total Experiences", str(summary["total_experiences"]))
        table.add_row("Avg Episode Reward", f"{summary['avg_episode_reward']:.2f}")
        table.add_row("Current Epsilon", f"{summary['current_epsilon']:.4f}")
        
        console.print(table)
        
        if summary["top_actions"]:
            top_table = Table(title="Top Actions by Q-Value")
            top_table.add_column("State", style="cyan")
            top_table.add_column("Action", style="yellow")
            top_table.add_column("Q-Value", style="green")
            
            for item in summary["top_actions"][:5]:
                top_table.add_row(
                    item["state"][:40],
                    item["action"],
                    f"{item['q_value']:.2f}"
                )
            
            console.print(top_table)


if __name__ == "__main__":
    # Demo usage
    console.print("[bold]Reinforcement Learning Engine Demo[/bold]\n")
    
    engine = RLEngine()
    
    # Simulate some learning
    for episode in range(10):
        # Create sample lead
        lead = {
            "icp_tier": random.choice(["tier_1", "tier_2", "tier_3"]),
            "intent_score": random.randint(20, 100),
            "source_type": random.choice(["competitor_follower", "event_attendee", "post_commenter"])
        }
        
        state = engine.get_state(lead)
        
        # Select action
        action = engine.select_action(state, "template")
        
        # Simulate outcome
        outcome = {
            "email_opened": random.randint(0, 1),
            "reply_received": random.random() > 0.8,
            "meeting_booked": random.random() > 0.95
        }
        
        reward = engine.calculate_reward(outcome)
        
        # Update (using same state as next_state for demo)
        engine.update(state, action, reward, state)
        
        console.print(f"Episode {episode + 1}: Action={action}, Reward={reward:.1f}")
    
    console.print()
    engine.print_policy_table()
    engine.save_policy()
