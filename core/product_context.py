#!/usr/bin/env python3
"""
Product Context Provider for Agent Knowledge
=============================================
Provides all agents with full context of ChiefAIOfficer.com product offerings,
pricing, methodology, and sales context.

This module loads the pitchdeck knowledge from .hive-mind/knowledge/company/
and exposes it for agent context injection.

Usage:
    from core.product_context import ProductContext
    
    ctx = ProductContext()
    
    # Get full product catalog for agent context
    products = ctx.get_products()
    
    # Get specific product details
    enterprise = ctx.get_product("enterprise_plan")
    
    # Get sales context for agent messaging
    sales_ctx = ctx.get_sales_context()
    
    # Get pricing for proposals
    pricing = ctx.get_pricing_summary()
    
    # Check if lead qualifies
    qualified = ctx.check_qualification(lead_data)
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


PROJECT_ROOT = Path(__file__).parent.parent
KNOWLEDGE_PATH = PROJECT_ROOT / ".hive-mind" / "knowledge" / "company"


class ProductContext:
    """
    Centralized product knowledge for all agents.
    
    Loads and exposes:
    - Product offerings (prices, features, duration)
    - M.A.P. Framework methodology
    - Value propositions and differentiators
    - Typical ROI results
    - Qualification/disqualification criteria
    - Case studies and social proof
    - CTAs and booking links
    """
    
    def __init__(self, knowledge_path: Optional[Path] = None):
        self.knowledge_path = knowledge_path or KNOWLEDGE_PATH
        self._product_data: Optional[Dict[str, Any]] = None
        self._sales_context: Optional[str] = None
        self._load_knowledge()
    
    def _load_knowledge(self):
        """Load product knowledge from JSON files."""
        product_file = self.knowledge_path / "product_offerings.json"
        sales_file = self.knowledge_path / "sales_context.md"
        
        if product_file.exists():
            try:
                with open(product_file, 'r', encoding='utf-8') as f:
                    self._product_data = json.load(f)
            except Exception as e:
                print(f"[ProductContext] Failed to load product_offerings.json: {e}")
                self._product_data = {}
        else:
            self._product_data = {}
        
        if sales_file.exists():
            try:
                with open(sales_file, 'r', encoding='utf-8') as f:
                    self._sales_context = f.read()
            except Exception as e:
                print(f"[ProductContext] Failed to load sales_context.md: {e}")
                self._sales_context = ""
        else:
            self._sales_context = ""
    
    # =========================================================================
    # PRODUCT ACCESS
    # =========================================================================
    
    def get_products(self) -> Dict[str, Any]:
        """Get all product offerings."""
        return self._product_data.get("products", {})
    
    def get_product(self, product_key: str) -> Optional[Dict[str, Any]]:
        """Get specific product by key."""
        return self._product_data.get("products", {}).get(product_key)
    
    def get_product_names(self) -> List[str]:
        """Get list of all product names."""
        return list(self._product_data.get("products", {}).keys())
    
    def get_pricing_summary(self) -> Dict[str, str]:
        """Get pricing summary for all products."""
        products = self._product_data.get("products", {})
        return {
            name: product.get("price_display", "Contact for pricing")
            for name, product in products.items()
        }
    
    # =========================================================================
    # METHODOLOGY ACCESS
    # =========================================================================
    
    def get_methodology(self) -> Dict[str, Any]:
        """Get M.A.P. Framework methodology details."""
        return self._product_data.get("methodology", {})
    
    def get_methodology_phases(self) -> List[Dict[str, Any]]:
        """Get M.A.P. Framework phases."""
        return self._product_data.get("methodology", {}).get("phases", [])
    
    def get_deliverables(self) -> List[str]:
        """Get key deliverables."""
        return self._product_data.get("methodology", {}).get("deliverables", [])
    
    # =========================================================================
    # VALUE PROPS & RESULTS
    # =========================================================================
    
    def get_typical_results(self) -> Dict[str, str]:
        """Get typical ROI/results metrics."""
        return self._product_data.get("typical_results", {})
    
    def get_differentiators(self) -> List[Dict[str, str]]:
        """Get key differentiators."""
        return self._product_data.get("differentiators", [])
    
    def get_guarantees(self) -> Dict[str, str]:
        """Get guarantees offered."""
        return self._product_data.get("guarantees", {})
    
    # =========================================================================
    # QUALIFICATION
    # =========================================================================
    
    def get_ideal_client_profile(self) -> Dict[str, List[str]]:
        """Get ICP criteria."""
        return self._product_data.get("ideal_client_profile", {})
    
    def get_disqualifiers(self) -> List[str]:
        """Get disqualification signals."""
        return self._product_data.get("ideal_client_profile", {}).get("disqualifiers", [])
    
    def check_qualification(self, lead_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if a lead qualifies based on ICP.
        
        Args:
            lead_data: Lead information to evaluate
            
        Returns:
            Dict with qualified status, score, and reasons
        """
        disqualifiers = self.get_disqualifiers()
        qualification_criteria = self._product_data.get("ideal_client_profile", {}).get(
            "choose_fractional_caio_when", []
        )
        
        score = 0
        max_score = len(qualification_criteria) * 10
        reasons = []
        disqualified = False
        disqualify_reasons = []
        
        # Check for disqualifiers in lead data
        notes = lead_data.get("notes", "").lower()
        company_info = lead_data.get("company_info", "").lower()
        combined = f"{notes} {company_info}"
        
        for disq in disqualifiers:
            disq_lower = disq.lower()
            if any(keyword in combined for keyword in disq_lower.split()[:3]):
                disqualified = True
                disqualify_reasons.append(disq)
        
        # Check positive criteria
        if lead_data.get("executive_sponsor"):
            score += 15
            reasons.append("Has executive sponsor")
        
        if lead_data.get("timeline_90_days") or "90 days" in combined or "measurable" in combined:
            score += 10
            reasons.append("Wants measurable outcomes in 90 days")
        
        if lead_data.get("workflows_identified") or "automat" in combined:
            score += 10
            reasons.append("Has identified workflows to automate")
        
        if lead_data.get("needs_training") or "training" in combined:
            score += 10
            reasons.append("Needs team training and change management")
        
        # Calculate percentage
        percentage = (score / max_score * 100) if max_score > 0 else 0
        
        return {
            "qualified": not disqualified and percentage >= 30,
            "score": score,
            "max_score": max_score,
            "percentage": percentage,
            "positive_signals": reasons,
            "disqualified": disqualified,
            "disqualify_reasons": disqualify_reasons
        }
    
    # =========================================================================
    # SALES CONTEXT
    # =========================================================================
    
    def get_sales_context(self) -> str:
        """Get full sales context markdown for agents."""
        return self._sales_context or ""
    
    def get_cta_urls(self) -> Dict[str, str]:
        """Get call-to-action URLs."""
        return self._product_data.get("cta_urls", {})
    
    def get_case_studies(self) -> List[Dict[str, Any]]:
        """Get case studies for social proof."""
        return self._product_data.get("case_studies", [])
    
    def get_capacity_note(self) -> str:
        """Get capacity limit statement for urgency."""
        return self._product_data.get("capacity_limit", "Limited availability")
    
    # =========================================================================
    # COMPANY INFO
    # =========================================================================
    
    def get_company_info(self) -> Dict[str, Any]:
        """Get company information."""
        return self._product_data.get("company", {})
    
    def get_founder_info(self) -> Dict[str, Any]:
        """Get founder information."""
        return self._product_data.get("company", {}).get("founder", {})
    
    # =========================================================================
    # AGENT CONTEXT INJECTION
    # =========================================================================
    
    def get_agent_context(self, agent_name: str) -> Dict[str, Any]:
        """
        Get tailored product context for a specific agent.
        
        Args:
            agent_name: Name of the agent (e.g., "CRAFTER", "ENRICHER")
            
        Returns:
            Dict with relevant context for that agent
        """
        base_context = {
            "company": self.get_company_info(),
            "cta_urls": self.get_cta_urls(),
            "capacity_limit": self.get_capacity_note()
        }
        
        if agent_name in ["CRAFTER", "COACH"]:
            # Sales/messaging agents need full product details
            return {
                **base_context,
                "products": self.get_products(),
                "pricing": self.get_pricing_summary(),
                "typical_results": self.get_typical_results(),
                "differentiators": self.get_differentiators(),
                "guarantees": self.get_guarantees(),
                "case_studies": self.get_case_studies(),
                "methodology": self.get_methodology()
            }
        
        elif agent_name in ["ENRICHER", "SEGMENTOR"]:
            # Research/qualification agents need ICP
            return {
                **base_context,
                "ideal_client_profile": self.get_ideal_client_profile(),
                "disqualifiers": self.get_disqualifiers(),
                "products": self.get_product_names()
            }
        
        elif agent_name in ["GATEKEEPER"]:
            # Approval agent needs pricing and guarantees
            return {
                **base_context,
                "pricing": self.get_pricing_summary(),
                "guarantees": self.get_guarantees(),
                "differentiators": self.get_differentiators()
            }
        
        elif agent_name in ["SCHEDULER"]:
            # Scheduling agent needs CTAs
            return {
                **base_context,
                "cta_urls": self.get_cta_urls(),
                "methodology": {"phases": self.get_methodology_phases()}
            }
        
        else:
            # Default: minimal context
            return base_context
    
    def get_full_context(self) -> Dict[str, Any]:
        """Get complete product context for logging/debugging."""
        return self._product_data or {}
    
    def format_for_prompt(self, agent_name: str) -> str:
        """
        Format product context as a string for prompt injection.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Formatted string for prompt context
        """
        ctx = self.get_agent_context(agent_name)
        
        lines = [
            "=== PRODUCT CONTEXT ===",
            f"Company: {ctx.get('company', {}).get('name', 'ChiefAIOfficer.com')}",
            f"Mission: {ctx.get('company', {}).get('mission', 'We make AI adoption easy')}",
            ""
        ]
        
        if "pricing" in ctx:
            lines.append("PRICING:")
            for product, price in ctx["pricing"].items():
                lines.append(f"  - {product}: {price}")
            lines.append("")
        
        if "typical_results" in ctx:
            lines.append("TYPICAL RESULTS:")
            for metric, value in ctx["typical_results"].items():
                lines.append(f"  - {metric}: {value}")
            lines.append("")
        
        if "guarantees" in ctx:
            lines.append("GUARANTEES:")
            for guarantee, desc in ctx["guarantees"].items():
                lines.append(f"  - {guarantee}: {desc}")
            lines.append("")
        
        lines.append(f"CTA: {ctx.get('cta_urls', {}).get('executive_briefing', 'https://caio.cx/ai-exec-briefing-call')}")
        lines.append(f"CAPACITY: {ctx.get('capacity_limit', 'Limited to 10 companies per month')}")
        lines.append("=== END PRODUCT CONTEXT ===")
        
        return "\n".join(lines)


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_product_context_instance: Optional[ProductContext] = None


def get_product_context() -> ProductContext:
    """Get singleton ProductContext instance."""
    global _product_context_instance
    if _product_context_instance is None:
        _product_context_instance = ProductContext()
    return _product_context_instance


# =============================================================================
# CLI DEMO
# =============================================================================

if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    
    console = Console()
    console.print("\n[bold blue]Product Context Demo[/bold blue]\n")
    
    ctx = ProductContext()
    
    # Show products
    console.print("[bold]Product Offerings:[/bold]")
    pricing = ctx.get_pricing_summary()
    
    table = Table()
    table.add_column("Product", style="cyan")
    table.add_column("Price", style="green")
    
    for product, price in pricing.items():
        table.add_row(product, price)
    
    console.print(table)
    
    # Show typical results
    console.print("\n[bold]Typical Results:[/bold]")
    for metric, value in ctx.get_typical_results().items():
        console.print(f"  • {metric}: {value}")
    
    # Show agent context example
    console.print("\n[bold]Agent Context (CRAFTER):[/bold]")
    crafter_ctx = ctx.format_for_prompt("CRAFTER")
    console.print(Panel(crafter_ctx, title="Prompt Context", border_style="blue"))
    
    # Test qualification
    console.print("\n[bold]Qualification Test:[/bold]")
    test_lead = {
        "executive_sponsor": True,
        "timeline_90_days": True,
        "notes": "Looking to automate sales processes"
    }
    result = ctx.check_qualification(test_lead)
    console.print(f"  Qualified: {result['qualified']}")
    console.print(f"  Score: {result['score']}/{result['max_score']} ({result['percentage']:.0f}%)")
    console.print(f"  Signals: {result['positive_signals']}")
    
    console.print("\n[green]Demo complete![/green]")
