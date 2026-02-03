#!/usr/bin/env python3
"""
Daily Report Generator for Revenue Swarm Operations.

Generates a comprehensive daily summary from pipeline runs, self-annealing state,
and RL policy data.

Usage:
    python execution/generate_daily_report.py              # Generate for today
    python execution/generate_daily_report.py --days 7     # Last 7 days summary
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

PROJECT_ROOT = Path(__file__).parent.parent
HIVE_MIND = PROJECT_ROOT / ".hive-mind"
PIPELINE_RUNS_DIR = HIVE_MIND / "pipeline_runs"
REPORTS_DIR = HIVE_MIND / "reports" / "daily"

TOKEN_COST_PER_1K_INPUT = 0.0025
TOKEN_COST_PER_1K_OUTPUT = 0.01
ESTIMATED_TOKENS_PER_LEAD = 500
ESTIMATED_TOKENS_PER_CAMPAIGN = 2000


def load_json_safe(path: Path) -> dict | None:
    """Load JSON file safely, returning None if not found or invalid."""
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        console.print(f"[yellow]Warning: Could not load {path}: {e}[/yellow]")
    return None


def get_pipeline_runs_in_range(start_date: datetime, end_date: datetime) -> list[dict]:
    """Get all pipeline runs within the specified date range."""
    runs = []
    if not PIPELINE_RUNS_DIR.exists():
        return runs

    for run_file in PIPELINE_RUNS_DIR.glob("run_*.json"):
        if "_campaigns" in run_file.name:
            continue
        
        run_data = load_json_safe(run_file)
        if not run_data:
            continue

        started_at = run_data.get("started_at")
        if not started_at:
            continue

        try:
            run_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            run_time = run_time.replace(tzinfo=None)
            
            if start_date <= run_time <= end_date:
                runs.append(run_data)
        except (ValueError, TypeError):
            continue

    return runs


def calculate_pipeline_metrics(runs: list[dict]) -> dict:
    """Calculate metrics from pipeline runs."""
    if not runs:
        return {
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "success_rate": 0.0,
            "leads_processed": 0,
            "campaigns_created": 0,
            "stage_durations": {},
            "stage_success_rates": {},
            "errors": [],
        }

    total_runs = len(runs)
    successful_runs = sum(1 for r in runs if r.get("total_errors", 0) == 0)
    failed_runs = total_runs - successful_runs
    
    leads_processed = sum(r.get("total_leads_processed", 0) for r in runs)
    campaigns_created = sum(r.get("total_campaigns_created", 0) for r in runs)
    
    stage_durations: dict[str, list[float]] = defaultdict(list)
    stage_successes: dict[str, list[bool]] = defaultdict(list)
    all_errors: list[str] = []
    
    for run in runs:
        for stage in run.get("stages", []):
            stage_name = stage.get("stage", "unknown")
            duration = stage.get("duration_ms", 0)
            success = stage.get("success", False)
            
            stage_durations[stage_name].append(duration)
            stage_successes[stage_name].append(success)
            
            for error in stage.get("errors", []):
                all_errors.append(f"[{stage_name}] {error}")
    
    avg_durations = {
        stage: sum(durations) / len(durations) if durations else 0
        for stage, durations in stage_durations.items()
    }
    
    stage_success_rates = {
        stage: (sum(successes) / len(successes) * 100) if successes else 0
        for stage, successes in stage_successes.items()
    }
    
    return {
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "failed_runs": failed_runs,
        "success_rate": (successful_runs / total_runs * 100) if total_runs > 0 else 0,
        "leads_processed": leads_processed,
        "campaigns_created": campaigns_created,
        "stage_durations": avg_durations,
        "stage_success_rates": stage_success_rates,
        "errors": all_errors[:10],
    }


def estimate_token_usage(metrics: dict) -> dict:
    """Estimate token usage and cost."""
    leads = metrics.get("leads_processed", 0)
    campaigns = metrics.get("campaigns_created", 0)
    
    input_tokens = leads * ESTIMATED_TOKENS_PER_LEAD
    output_tokens = campaigns * ESTIMATED_TOKENS_PER_CAMPAIGN
    
    input_cost = (input_tokens / 1000) * TOKEN_COST_PER_1K_INPUT
    output_cost = (output_tokens / 1000) * TOKEN_COST_PER_1K_OUTPUT
    
    return {
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": round(input_cost + output_cost, 4),
    }


def get_self_annealing_insights() -> dict:
    """Extract insights from self-annealing state."""
    state_path = HIVE_MIND / "self_annealing_state.json"
    state = load_json_safe(state_path)
    
    if not state:
        return {
            "epsilon": None,
            "success_patterns": [],
            "failure_patterns": [],
            "recommendations": [],
            "metrics": {},
        }
    
    patterns = state.get("patterns", {})
    success_patterns = []
    failure_patterns = []
    
    for pattern_id, pattern_data in patterns.items():
        pattern_info = {
            "id": pattern_id,
            "type": pattern_data.get("pattern_type", "unknown"),
            "frequency": pattern_data.get("frequency", 0),
            "confidence": pattern_data.get("confidence", 0),
            "context": pattern_data.get("context", {}),
        }
        
        if pattern_data.get("pattern_type") == "success":
            success_patterns.append(pattern_info)
        else:
            failure_patterns.append(pattern_info)
    
    success_patterns.sort(key=lambda x: x["frequency"], reverse=True)
    failure_patterns.sort(key=lambda x: x["frequency"], reverse=True)
    
    refinements = state.get("refinements", [])
    unique_recommendations = []
    seen_suggestions = set()
    
    for ref in refinements:
        suggestion = ref.get("suggestion", "")
        if suggestion and suggestion not in seen_suggestions:
            seen_suggestions.add(suggestion)
            unique_recommendations.append({
                "target": ref.get("target", "unknown"),
                "suggestion": suggestion,
                "confidence": ref.get("confidence", 0),
                "reason": ref.get("reason", ""),
            })
    
    return {
        "epsilon": state.get("epsilon"),
        "success_patterns": success_patterns[:3],
        "failure_patterns": failure_patterns[:3],
        "recommendations": unique_recommendations[:5],
        "metrics": state.get("metrics", {}),
    }


def get_rl_policy_info() -> dict:
    """Extract information from RL policy."""
    policy_path = HIVE_MIND / "rl_policy.json"
    policy = load_json_safe(policy_path)
    
    if not policy:
        return {
            "epsilon": None,
            "q_table_size": 0,
            "episode_count": 0,
            "action_counts": {},
        }
    
    return {
        "epsilon": policy.get("epsilon"),
        "q_table_size": len(policy.get("q_table", {})),
        "episode_count": len(policy.get("episode_rewards", [])),
        "action_counts": policy.get("action_counts", {}),
    }


def generate_report(days: int = 1) -> dict:
    """Generate the daily report."""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    runs = get_pipeline_runs_in_range(start_date, end_date)
    pipeline_metrics = calculate_pipeline_metrics(runs)
    token_usage = estimate_token_usage(pipeline_metrics)
    annealing_insights = get_self_annealing_insights()
    rl_info = get_rl_policy_info()
    
    report = {
        "report_type": "daily" if days == 1 else f"{days}_day_summary",
        "generated_at": datetime.now().isoformat(),
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days,
        },
        "pipeline_metrics": pipeline_metrics,
        "token_usage": token_usage,
        "self_annealing": annealing_insights,
        "rl_policy": rl_info,
    }
    
    return report


def format_report_markdown(report: dict) -> str:
    """Format report as markdown."""
    period = report["period"]
    metrics = report["pipeline_metrics"]
    tokens = report["token_usage"]
    annealing = report["self_annealing"]
    rl = report["rl_policy"]
    
    md = f"""# 📊 Revenue Swarm Daily Report

**Generated:** {report['generated_at']}  
**Period:** {period['start'][:10]} to {period['end'][:10]} ({period['days']} day{'s' if period['days'] > 1 else ''})

---

## 🚀 Pipeline Metrics

| Metric | Value |
|--------|-------|
| Total Pipeline Runs | {metrics['total_runs']} |
| Successful Runs | {metrics['successful_runs']} |
| Failed Runs | {metrics['failed_runs']} |
| **Success Rate** | **{metrics['success_rate']:.1f}%** |
| Leads Processed | {metrics['leads_processed']} |
| Campaigns Created | {metrics['campaigns_created']} |

### Stage Performance

| Stage | Avg Duration (ms) | Success Rate |
|-------|-------------------|--------------|
"""
    
    for stage, duration in metrics.get("stage_durations", {}).items():
        success_rate = metrics.get("stage_success_rates", {}).get(stage, 0)
        md += f"| {stage.title()} | {duration:.2f} | {success_rate:.1f}% |\n"
    
    if not metrics.get("stage_durations"):
        md += "| No data | - | - |\n"
    
    md += f"""
---

## 💰 Token Usage & Cost Estimate

| Metric | Value |
|--------|-------|
| Estimated Input Tokens | {tokens['estimated_input_tokens']:,} |
| Estimated Output Tokens | {tokens['estimated_output_tokens']:,} |
| **Total Tokens** | **{tokens['total_tokens']:,}** |
| **Estimated Cost** | **${tokens['estimated_cost_usd']:.4f}** |

---

## 🔥 Self-Annealing Insights

**Current Epsilon (Exploration Rate):** {f"{annealing['epsilon']:.4f}" if annealing['epsilon'] else 'N/A'}

### Annealing Metrics

| Metric | Value |
|--------|-------|
| Total Outcomes | {annealing['metrics'].get('total_outcomes', 0)} |
| Success Count | {annealing['metrics'].get('success_count', 0)} |
| Failure Count | {annealing['metrics'].get('failure_count', 0)} |
| Patterns Detected | {annealing['metrics'].get('patterns_detected', 0)} |
| Annealing Steps | {annealing['metrics'].get('annealing_steps', 0)} |

### Top Success Patterns

"""
    
    if annealing['success_patterns']:
        for i, pattern in enumerate(annealing['success_patterns'], 1):
            md += f"{i}. **{pattern['id']}** - Frequency: {pattern['frequency']}, Confidence: {pattern['confidence']:.2f}\n"
    else:
        md += "- No success patterns detected\n"
    
    md += "\n### Top Failure Patterns\n\n"
    
    if annealing['failure_patterns']:
        for i, pattern in enumerate(annealing['failure_patterns'], 1):
            md += f"{i}. **{pattern['id']}** - Frequency: {pattern['frequency']}, Confidence: {pattern['confidence']:.2f}\n"
    else:
        md += "- No failure patterns detected\n"
    
    md += "\n### Recommendations\n\n"
    
    if annealing['recommendations']:
        for rec in annealing['recommendations']:
            md += f"- **[{rec['target'].upper()}]** {rec['suggestion']} (Confidence: {rec['confidence']:.2f})\n"
            md += f"  - Reason: {rec['reason']}\n"
    else:
        md += "- No recommendations available\n"
    
    md += f"""
---

## 🧠 RL Policy State

| Metric | Value |
|--------|-------|
| Current Epsilon | {f"{rl['epsilon']:.4f}" if rl['epsilon'] else 'N/A'} |
| Q-Table Entries | {rl['q_table_size']} |
| Episodes Completed | {rl['episode_count']} |

"""
    
    if rl['action_counts']:
        md += "### Action Distribution\n\n"
        for action, count in rl['action_counts'].items():
            md += f"- **{action}**: {count}\n"
    
    if metrics['errors']:
        md += "\n---\n\n## ⚠️ Recent Errors\n\n"
        for error in metrics['errors']:
            md += f"- `{error}`\n"
    
    md += f"""
---

*Report generated by Revenue Swarm Daily Report Generator*
"""
    
    return md


def print_console_summary(report: dict) -> None:
    """Print a summary to the console using rich."""
    metrics = report["pipeline_metrics"]
    tokens = report["token_usage"]
    annealing = report["self_annealing"]
    period = report["period"]
    
    console.print()
    console.print(Panel.fit(
        f"[bold blue]Revenue Swarm Daily Report[/bold blue]\n"
        f"Period: {period['start'][:10]} to {period['end'][:10]}",
        border_style="blue"
    ))
    
    pipeline_table = Table(title="Pipeline Metrics", show_header=True, header_style="bold cyan")
    pipeline_table.add_column("Metric", style="cyan")
    pipeline_table.add_column("Value", style="green", justify="right")
    
    pipeline_table.add_row("Total Runs", str(metrics['total_runs']))
    pipeline_table.add_row("Successful", str(metrics['successful_runs']))
    pipeline_table.add_row("Failed", str(metrics['failed_runs']))
    pipeline_table.add_row("Success Rate", f"{metrics['success_rate']:.1f}%")
    pipeline_table.add_row("Leads Processed", str(metrics['leads_processed']))
    pipeline_table.add_row("Campaigns Created", str(metrics['campaigns_created']))
    
    console.print(pipeline_table)
    console.print()
    
    stage_table = Table(title="Stage Performance", show_header=True, header_style="bold magenta")
    stage_table.add_column("Stage", style="magenta")
    stage_table.add_column("Avg Duration (ms)", justify="right")
    stage_table.add_column("Success Rate", justify="right")
    
    for stage, duration in metrics.get("stage_durations", {}).items():
        success_rate = metrics.get("stage_success_rates", {}).get(stage, 0)
        stage_table.add_row(
            stage.title(),
            f"{duration:.2f}",
            f"{success_rate:.1f}%"
        )
    
    if metrics.get("stage_durations"):
        console.print(stage_table)
        console.print()
    
    cost_table = Table(title="Token Usage & Cost", show_header=True, header_style="bold yellow")
    cost_table.add_column("Metric", style="yellow")
    cost_table.add_column("Value", style="green", justify="right")
    
    cost_table.add_row("Total Tokens", f"{tokens['total_tokens']:,}")
    cost_table.add_row("Estimated Cost", f"${tokens['estimated_cost_usd']:.4f}")
    
    console.print(cost_table)
    console.print()
    
    annealing_table = Table(title="Self-Annealing Insights", show_header=True, header_style="bold red")
    annealing_table.add_column("Metric", style="red")
    annealing_table.add_column("Value", style="green", justify="right")
    
    epsilon_val = f"{annealing['epsilon']:.4f}" if annealing['epsilon'] else "N/A"
    annealing_table.add_row("Epsilon (Exploration)", epsilon_val)
    annealing_table.add_row("Success Patterns", str(len(annealing['success_patterns'])))
    annealing_table.add_row("Failure Patterns", str(len(annealing['failure_patterns'])))
    annealing_table.add_row("Recommendations", str(len(annealing['recommendations'])))
    
    console.print(annealing_table)
    console.print()
    
    if annealing['recommendations']:
        console.print("[bold]Top Recommendation:[/bold]")
        rec = annealing['recommendations'][0]
        console.print(f"  [{rec['target'].upper()}] {rec['suggestion']}")
        console.print()
    
    if metrics['errors']:
        console.print(f"[yellow]Warning: {len(metrics['errors'])} error(s) in this period[/yellow]")
        console.print()


def save_report(report: dict, report_date: str) -> Path:
    """Save the report to the reports directory."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    report_path = REPORTS_DIR / f"{report_date}.md"
    markdown_content = format_report_markdown(report)
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)
    
    return report_path


def main():
    parser = argparse.ArgumentParser(
        description="Generate daily summary report for Revenue Swarm operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python execution/generate_daily_report.py              # Generate for today
    python execution/generate_daily_report.py --days 7     # Last 7 days summary
    python execution/generate_daily_report.py --json       # Output as JSON
    python execution/generate_daily_report.py --quiet      # No console output
        """
    )
    
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to include in report (default: 1)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON instead of markdown"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress console output"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Custom output file path"
    )
    
    args = parser.parse_args()
    
    report = generate_report(days=args.days)
    
    if not args.quiet:
        print_console_summary(report)
    
    report_date = datetime.now().strftime("%Y-%m-%d")
    if args.days > 1:
        report_date = f"{report_date}_{args.days}d"
    
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        ext = ".json" if args.json else ".md"
        output_path = REPORTS_DIR / f"{report_date}{ext}"
    
    if args.json or (args.output and args.output.endswith(".json")):
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
    else:
        markdown_content = format_report_markdown(report)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
    
    if not args.quiet:
        console.print(f"[green]Report saved to:[/green] {output_path}")


if __name__ == "__main__":
    main()
