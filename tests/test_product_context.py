#!/usr/bin/env python3
"""
Unit tests for ProductContext module.
Tests product knowledge loading and agent context injection.
"""

import os
import sys
import json
import pytest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.product_context import ProductContext, get_product_context


class TestProductContext:
    """Test ProductContext functionality."""
    
    @pytest.fixture
    def context(self):
        """Create ProductContext instance."""
        return ProductContext()
    
    def test_initialization(self, context):
        """Test that ProductContext initializes properly."""
        assert context is not None
        assert context._product_data is not None
    
    def test_get_products(self, context):
        """Test getting all products."""
        products = context.get_products()
        assert isinstance(products, dict)
        
        # Should have key products
        expected_products = [
            "ai_opportunity_audit",
            "ai_executive_certification_workshop",
            "on_site_plan",
            "enterprise_plan",
            "ai_consulting"
        ]
        
        for prod in expected_products:
            assert prod in products, f"Missing product: {prod}"
    
    def test_get_product_by_key(self, context):
        """Test getting specific product."""
        audit = context.get_product("ai_opportunity_audit")
        assert audit is not None
        assert audit.get("price") == 10000
        assert "2-4 weeks" in audit.get("duration", "")
    
    def test_get_pricing_summary(self, context):
        """Test pricing summary generation."""
        pricing = context.get_pricing_summary()
        assert isinstance(pricing, dict)
        
        # Check specific prices
        assert "$10,000" in pricing.get("ai_opportunity_audit", "")
        assert "$12,000" in pricing.get("ai_executive_certification_workshop", "")
        assert "$14,500" in pricing.get("on_site_plan", "")
        assert "$800" in pricing.get("ai_consulting", "")
    
    def test_get_methodology(self, context):
        """Test M.A.P. Framework methodology."""
        methodology = context.get_methodology()
        assert methodology.get("name") == "M.A.P. Framework"
        
        phases = methodology.get("phases", [])
        assert len(phases) >= 5  # Pre-Rollout, Kickoff, Model, Assess, Perform
        
        phase_names = [p.get("name") for p in phases]
        assert "Model" in phase_names
        assert "Assess" in phase_names
        assert "Perform" in phase_names
    
    def test_get_typical_results(self, context):
        """Test typical ROI results."""
        results = context.get_typical_results()
        assert isinstance(results, dict)
        
        # Check key metrics
        assert "operational_cost_reduction" in results
        assert "efficiency_improvement" in results
        assert "20-30%" in results.get("operational_cost_reduction", "")
        assert "40%" in results.get("efficiency_improvement", "")
    
    def test_get_differentiators(self, context):
        """Test value proposition differentiators."""
        differentiators = context.get_differentiators()
        assert isinstance(differentiators, list)
        assert len(differentiators) >= 4
        
        names = [d.get("name") for d in differentiators]
        assert "No Jargon, No Guesswork" in names
        assert "Fixed-Fee Pricing" in names
        assert "Proof or Pause" in names
    
    def test_get_disqualifiers(self, context):
        """Test disqualification signals."""
        disqualifiers = context.get_disqualifiers()
        assert isinstance(disqualifiers, list)
        assert len(disqualifiers) >= 10
        
        # Check key disqualifiers
        disq_text = " ".join(disqualifiers).lower()
        assert "executive sponsor" in disq_text
        assert "ai magic" in disq_text
        assert "ai use policy" in disq_text
    
    def test_check_qualification_positive(self, context):
        """Test lead qualification with positive signals."""
        lead = {
            "executive_sponsor": True,
            "timeline_90_days": True,
            "workflows_identified": True,
            "needs_training": True,
            "notes": "VP of Sales seeking AI solutions for team efficiency"
        }
        
        result = context.check_qualification(lead)
        # Should have positive score and signals
        assert result["score"] > 0
        assert len(result["positive_signals"]) >= 2
        # Qualification depends on threshold - just verify scoring works
        assert result["percentage"] > 0
    
    def test_check_qualification_disqualified(self, context):
        """Test lead disqualification."""
        lead = {
            "notes": "No executive sponsor available, expecting AI magic"
        }
        
        result = context.check_qualification(lead)
        assert result["disqualified"] is True or result["qualified"] is False
    
    def test_get_cta_urls(self, context):
        """Test CTA URL retrieval."""
        urls = context.get_cta_urls()
        assert "executive_briefing" in urls
        assert "caio.cx" in urls.get("executive_briefing", "")
    
    def test_get_case_studies(self, context):
        """Test case studies retrieval."""
        cases = context.get_case_studies()
        assert isinstance(cases, list)
        assert len(cases) >= 3
        
        clients = [c.get("client") for c in cases]
        assert "Frazer LTD" in clients
        assert "Immatics Biotechnologies" in clients
    
    def test_get_company_info(self, context):
        """Test company info retrieval."""
        company = context.get_company_info()
        assert company.get("name") == "ChiefAIOfficer.com"
        assert "AI adoption easy" in company.get("mission", "")
        
        founder = company.get("founder", {})
        assert founder.get("name") == "Chris Daigle"
    
    def test_get_agent_context_crafter(self, context):
        """Test agent context for CRAFTER."""
        agent_ctx = context.get_agent_context("CRAFTER")
        
        # CRAFTER should have full product info
        assert "products" in agent_ctx
        assert "pricing" in agent_ctx
        assert "typical_results" in agent_ctx
        assert "differentiators" in agent_ctx
        assert "guarantees" in agent_ctx
        assert "case_studies" in agent_ctx
        assert "methodology" in agent_ctx
    
    def test_get_agent_context_enricher(self, context):
        """Test agent context for ENRICHER."""
        agent_ctx = context.get_agent_context("ENRICHER")
        
        # ENRICHER should have ICP info
        assert "ideal_client_profile" in agent_ctx
        assert "disqualifiers" in agent_ctx
        assert "products" in agent_ctx
    
    def test_get_agent_context_scheduler(self, context):
        """Test agent context for SCHEDULER."""
        agent_ctx = context.get_agent_context("SCHEDULER")
        
        # SCHEDULER should have CTAs
        assert "cta_urls" in agent_ctx
        assert "methodology" in agent_ctx
    
    def test_format_for_prompt(self, context):
        """Test prompt formatting."""
        prompt_ctx = context.format_for_prompt("CRAFTER")
        
        assert "PRODUCT CONTEXT" in prompt_ctx
        assert "ChiefAIOfficer.com" in prompt_ctx
        assert "PRICING:" in prompt_ctx
        assert "TYPICAL RESULTS:" in prompt_ctx
        assert "GUARANTEES:" in prompt_ctx
        assert "CTA:" in prompt_ctx
        assert "caio.cx" in prompt_ctx
    
    def test_singleton_instance(self):
        """Test singleton pattern."""
        ctx1 = get_product_context()
        ctx2 = get_product_context()
        assert ctx1 is ctx2
    
    def test_capacity_limit(self, context):
        """Test capacity limit note."""
        capacity = context.get_capacity_note()
        assert "10" in capacity
        assert "month" in capacity.lower()
    
    def test_guarantees(self, context):
        """Test guarantee statements."""
        guarantees = context.get_guarantees()
        assert "transparent_tracking" in guarantees or "risk_guarantee" in guarantees
        
        # Check risk guarantee
        guarantee_text = " ".join(guarantees.values()).lower()
        assert "roi" in guarantee_text


class TestProductKnowledgeIntegration:
    """Test product knowledge integration with self-annealing engine."""
    
    def test_self_annealing_product_seeding(self):
        """Test that self-annealing engine seeds product knowledge."""
        from core.self_annealing_engine import SelfAnnealingPipeline
        
        pipeline = SelfAnnealingPipeline()
        status = pipeline.get_status()
        
        # Should have product knowledge loaded
        assert status.get("product_knowledge_loaded") is True
        
        # Reasoning bank should have product entries
        assert status["reasoning_bank_size"] > 0
    
    def test_product_retrieval_from_reasoning_bank(self):
        """Test retrieving product knowledge via similarity search."""
        from core.self_annealing_engine import SelfAnnealingPipeline
        
        pipeline = SelfAnnealingPipeline()
        
        # Search for pricing info
        results = pipeline.retrieve("product pricing cost investment", k=5)
        assert len(results) > 0
        
        # Check that product entries are found
        found_product = False
        for entry, similarity in results:
            if entry.context.get("category") == "product_offering":
                found_product = True
                break
        
        assert found_product, "Should find product entries in reasoning bank"
    
    def test_methodology_retrieval(self):
        """Test retrieving M.A.P. Framework methodology."""
        from core.self_annealing_engine import SelfAnnealingPipeline
        
        pipeline = SelfAnnealingPipeline()
        
        # Search for methodology
        results = pipeline.retrieve("M.A.P. Framework implementation phases", k=5)
        assert len(results) > 0
        
        # Check for methodology entries
        found_methodology = False
        for entry, similarity in results:
            if entry.context.get("category") == "methodology":
                found_methodology = True
                break
        
        assert found_methodology, "Should find methodology entries"
    
    def test_disqualifier_retrieval(self):
        """Test retrieving disqualification patterns."""
        from core.self_annealing_engine import SelfAnnealingPipeline
        
        pipeline = SelfAnnealingPipeline()
        
        # Search for disqualifiers
        results = pipeline.retrieve("no executive sponsor budget owner", k=5)
        assert len(results) > 0
        
        # Check for disqualifier entries
        found_disqualifier = False
        for entry, similarity in results:
            if entry.context.get("category") == "disqualifier":
                found_disqualifier = True
                break
        
        assert found_disqualifier, "Should find disqualifier entries"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
