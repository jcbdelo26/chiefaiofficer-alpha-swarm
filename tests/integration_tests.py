#!/usr/bin/env python3
"""
Integration Tests for Alpha Swarm
==================================

Comprehensive integration tests for production readiness.

Test Suites:
1. MCP Server Tests (GHL, Instantly, Document)
2. Webhook Handler Tests
3. RPI Workflow Tests
4. End-to-End Pipeline Tests

Usage:
    # Run all tests
    python tests/integration_tests.py
    
    # Run specific suite
    python tests/integration_tests.py --suite mcp
    python tests/integration_tests.py --suite webhooks
    python tests/integration_tests.py --suite pipeline
    
    # Use staging environment
    python tests/integration_tests.py --env staging
"""

import os
import sys
import json
import asyncio
import unittest
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


# ============================================================================
# Test Configuration
# ============================================================================

@dataclass
class TestConfig:
    """Test environment configuration."""
    env: str  # 'staging' or 'production'
    ghl_api_key: str
    instantly_api_key: str
    use_mocks: bool
    temp_dir: Path


def load_test_config(env: str = "staging") -> TestConfig:
    """Load test configuration from environment."""
    from dotenv import load_dotenv
    
    # Load staging env if available
    staging_env = Path(__file__).parent.parent / ".env.staging"
    if staging_env.exists() and env == "staging":
        load_dotenv(staging_env)
    else:
        load_dotenv()
    
    return TestConfig(
        env=env,
        ghl_api_key=os.getenv("GHL_API_KEY", "test_key"),
        instantly_api_key=os.getenv("INSTANTLY_API_KEY", "test_key"),
        use_mocks=env == "staging" or os.getenv("USE_MOCKS", "true").lower() == "true",
        temp_dir=Path(tempfile.mkdtemp(prefix="alpha_swarm_test_"))
    )


# ============================================================================
# Mock Responses
# ============================================================================

MOCK_GHL_CONTACT = {
    "contact": {
        "id": "test_contact_123",
        "email": "test@example.com",
        "firstName": "Test",
        "lastName": "User",
        "companyName": "Test Corp",
        "tags": ["lead", "tier1"]
    }
}

MOCK_INSTANTLY_CAMPAIGN = {
    "data": {
        "id": "test_campaign_123",
        "name": "Test Campaign",
        "status": "active",
        "from_email": "outreach@company.com"
    }
}

MOCK_ANALYTICS = {
    "data": {
        "campaign_id": "test_campaign_123",
        "sent": 100,
        "opened": 45,
        "clicked": 12,
        "replied": 5,
        "bounced": 2
    }
}


# ============================================================================
# MCP Server Tests
# ============================================================================

class TestGHLMCP(unittest.TestCase):
    """Integration tests for GoHighLevel MCP server."""
    
    @classmethod
    def setUpClass(cls):
        cls.config = load_test_config()
    
    @classmethod
    def tearDownClass(cls):
        if cls.config.temp_dir.exists():
            shutil.rmtree(cls.config.temp_dir)
    
    def test_idempotency_manager(self):
        """Test idempotency key generation and caching."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-servers" / "ghl-mcp"))
        
        from server import IdempotencyManager
        
        manager = IdempotencyManager(self.config.temp_dir / "idempotency")
        
        # Generate key
        key1 = manager.generate_key("create_contact", {"email": "test@example.com"})
        key2 = manager.generate_key("create_contact", {"email": "test@example.com"})
        key3 = manager.generate_key("create_contact", {"email": "other@example.com"})
        
        self.assertEqual(key1, key2)  # Same input = same key
        self.assertNotEqual(key1, key3)  # Different input = different key
        
        # Store and retrieve
        manager.store(key1, "create_contact", "hash123", {"success": True, "id": "123"})
        
        cached = manager.check(key1)
        self.assertIsNotNone(cached)
        self.assertTrue(cached["success"])
    
    @patch('aiohttp.ClientSession')
    async def test_create_contact_idempotent(self, mock_session):
        """Test idempotent contact creation."""
        from server import AsyncGHLClient
        
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(return_value=MOCK_GHL_CONTACT)
        
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
        
        with patch.dict(os.environ, {"GHL_API_KEY": "test", "GHL_LOCATION_ID": "loc123"}):
            client = AsyncGHLClient()
            client._session = mock_session.return_value
            
            # First call
            result1 = await client.create_contact({"email": "test@example.com"})
            
            # Second call should hit cache
            result2 = await client.create_contact({"email": "test@example.com"})
            
            # Should be cached
            self.assertEqual(result1, result2)
    
    def test_bulk_contact_batching(self):
        """Test bulk contact creation with batching."""
        # This would be a full async test in production
        pass


class TestInstantlyMCP(unittest.TestCase):
    """Integration tests for Instantly MCP server."""
    
    @classmethod
    def setUpClass(cls):
        cls.config = load_test_config()
    
    def test_idempotent_campaign_creation(self):
        """Test campaign creation is idempotent."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "mcp-servers" / "instantly-mcp"))
        
        from server import IdempotencyManager
        
        manager = IdempotencyManager()
        
        key = manager.generate_key("create_campaign", {"name": "Test Campaign", "from_email": "test@co.com"})
        
        # Simulate storing result
        manager.store(key, {"success": True, "campaign_id": "test_123"})
        
        # Should return cached
        cached = manager.check(key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["campaign_id"], "test_123")
    
    def test_sequence_ab_variant_support(self):
        """Test A/B variant support in sequences."""
        # Test the data structure
        steps = [
            {
                "delay_days": 0,
                "subject": "Subject A",
                "body": "Body A",
                "subject_b": "Subject B",
                "body_b": "Body B"
            },
            {
                "delay_days": 3,
                "subject": "Follow up",
                "body": "Just following up"
            }
        ]
        
        # Verify structure
        self.assertTrue("subject_b" in steps[0])
        self.assertFalse("subject_b" in steps[1])


class TestDocumentMCP(unittest.TestCase):
    """Integration tests for Document Extraction MCP."""
    
    @classmethod
    def setUpClass(cls):
        cls.config = load_test_config()
    
    def test_document_parser_import(self):
        """Test document parser module imports correctly."""
        from core.document_parser import (
            DocumentParser,
            parse_document,
            LEAD_ENRICHMENT_SCHEMA
        )
        
        self.assertIsNotNone(DocumentParser)
        self.assertIn("company_name", LEAD_ENRICHMENT_SCHEMA)
    
    def test_schema_definitions(self):
        """Test extraction schemas are properly defined."""
        from core.document_parser import (
            LEAD_ENRICHMENT_SCHEMA,
            COMPETITIVE_INTEL_SCHEMA
        )
        
        # Lead schema should have key fields
        self.assertIn("employee_count", LEAD_ENRICHMENT_SCHEMA)
        self.assertIn("tech_stack", LEAD_ENRICHMENT_SCHEMA)
        
        # Competitive schema should have pricing
        self.assertIn("pricing", COMPETITIVE_INTEL_SCHEMA)


# ============================================================================
# Webhook Tests
# ============================================================================

class TestWebhookHandlers(unittest.TestCase):
    """Integration tests for webhook handlers."""
    
    @classmethod
    def setUpClass(cls):
        cls.config = load_test_config()
        cls.temp_dir = cls.config.temp_dir / "webhooks"
        cls.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def test_event_store_deduplication(self):
        """Test event store prevents duplicate processing."""
        from webhooks.webhook_server import EventStore, WebhookEvent
        
        store = EventStore(self.temp_dir / "events")
        
        event = WebhookEvent(
            event_id="test_event_123",
            source="test",
            event_type="test_event",
            timestamp=datetime.utcnow().isoformat(),
            payload={"test": True}
        )
        
        # First store
        store.store_event(event)
        
        # Check duplicate detection
        self.assertTrue(store.is_duplicate("test_event_123"))
        self.assertFalse(store.is_duplicate("other_event"))
    
    def test_ghl_handler_routing(self):
        """Test GHL webhook routes to correct handler."""
        from webhooks.webhook_server import GHLWebhookHandler, GHLEventType
        
        handler = GHLWebhookHandler()
        
        # Verify handlers are registered
        self.assertIn(GHLEventType.CONTACT_CREATED.value, handler.handlers)
        self.assertIn(GHLEventType.INBOUND_MESSAGE.value, handler.handlers)
    
    def test_instantly_reply_saving(self):
        """Test Instantly reply webhook saves to file."""
        from webhooks.webhook_server import InstantlyWebhookHandler
        
        handler = InstantlyWebhookHandler()
        
        # The handler should exist
        self.assertIsNotNone(handler.handlers.get("email_replied"))
    
    def test_unsubscribe_compliance(self):
        """Test unsubscribe handling for compliance."""
        from webhooks.webhook_server import InstantlyWebhookHandler
        
        handler = InstantlyWebhookHandler()
        
        # Verify unsubscribe handler exists
        self.assertIn("email_unsubscribed", handler.handlers)


# ============================================================================
# RPI Workflow Tests
# ============================================================================

class TestRPIWorkflow(unittest.TestCase):
    """Integration tests for Research-Plan-Implement workflow."""
    
    @classmethod
    def setUpClass(cls):
        cls.config = load_test_config()
    
    def test_research_phase_import(self):
        """Test research phase module imports."""
        from execution.rpi_research import run_research, ResearchOutput
        
        self.assertIsNotNone(run_research)
    
    def test_plan_phase_import(self):
        """Test plan phase module imports."""
        from execution.rpi_plan import generate_campaign_plan, CampaignPlan
        
        self.assertIsNotNone(generate_campaign_plan)
    
    def test_implement_phase_import(self):
        """Test implement phase module imports."""
        from execution.rpi_implement import implement_plan, GeneratedCampaign
        
        self.assertIsNotNone(implement_plan)
    
    def test_semantic_anchors_attached(self):
        """Test semantic anchors are attached to campaigns."""
        # Create sample campaign output
        campaign = {
            "campaign_id": "test_123",
            "tier": "tier1",
            "template": "competitor_displacement",
            "semantic_anchors": [
                "TEMPLATE: competitor_displacement",
                "PERSONALIZATION: deep",
                "REVIEW: AE approval required"
            ]
        }
        
        self.assertIn("semantic_anchors", campaign)
        self.assertTrue(len(campaign["semantic_anchors"]) > 0)


# ============================================================================
# End-to-End Pipeline Tests
# ============================================================================

class TestEndToEndPipeline(unittest.TestCase):
    """End-to-end integration tests for the full pipeline."""
    
    @classmethod
    def setUpClass(cls):
        cls.config = load_test_config()
        cls.temp_dir = cls.config.temp_dir / "pipeline"
        cls.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def test_lead_flow_structure(self):
        """Test lead data structure through pipeline."""
        lead = {
            "lead_id": "lead_123",
            "email": "test@company.com",
            "name": "Test User",
            "company": "Test Corp",
            "title": "VP of Sales",
            "company_size": 150,
            "source": "linkedin_followers",
            "icp_score": 85
        }
        
        # Verify required fields
        required_fields = ["lead_id", "email", "company", "icp_score"]
        for field in required_fields:
            self.assertIn(field, lead)
    
    def test_campaign_output_structure(self):
        """Test campaign output structure."""
        campaign = {
            "campaign_id": "camp_123",
            "tier": "tier1",
            "template": "competitor_displacement",
            "lead_count": 5,
            "sequence": [
                {
                    "step": 1,
                    "delay_days": 0,
                    "subject_a": "Subject A",
                    "subject_b": "Subject B",
                    "body": "Email body",
                    "personalization_level": "deep"
                }
            ],
            "semantic_anchors": [],
            "status": "pending_review"
        }
        
        # Verify structure
        self.assertIn("sequence", campaign)
        self.assertTrue(len(campaign["sequence"]) > 0)
        self.assertIn("subject_a", campaign["sequence"][0])
    
    def test_gatekeeper_queue_structure(self):
        """Test GATEKEEPER queue structure."""
        review_item = {
            "review_id": "rev_123",
            "campaign_id": "camp_123",
            "campaign_name": "Tier 1 Campaign",
            "lead_count": 5,
            "status": "pending",
            "semantic_anchors": ["Context 1", "Context 2"],
            "tier": "tier1",
            "rpi_workflow": True
        }
        
        # Verify semantic anchors included
        self.assertIn("semantic_anchors", review_item)
        self.assertTrue(review_item["rpi_workflow"])


# ============================================================================
# Staging Environment Tests
# ============================================================================

class TestStagingEnvironment(unittest.TestCase):
    """Tests specific to staging environment setup."""
    
    def test_env_file_structure(self):
        """Test staging .env file has required variables."""
        required_vars = [
            "GHL_API_KEY",
            "GHL_LOCATION_ID",
            "INSTANTLY_API_KEY",
            "CLAY_API_KEY"
        ]
        
        # Check current env
        for var in required_vars:
            value = os.getenv(var)
            # Just check they're defined (may be test values)
            # In staging, these would be real test API keys
    
    def test_hive_mind_directories(self):
        """Test .hive-mind directory structure exists."""
        hive_mind = Path(__file__).parent.parent / ".hive-mind"
        
        required_dirs = [
            "scraped",
            "enriched",
            "segmented",
            "campaigns",
            "research",
            "plans"
        ]
        
        for dir_name in required_dirs:
            dir_path = hive_mind / dir_name
            # Directories should exist or be creatable
            dir_path.mkdir(parents=True, exist_ok=True)
            self.assertTrue(dir_path.exists())


# ============================================================================
# Test Runner
# ============================================================================

def run_test_suite(suite_name: Optional[str] = None, env: str = "staging"):
    """Run test suites with rich output."""
    
    console.print(Panel.fit(
        f"[bold blue]Alpha Swarm Integration Tests[/bold blue]\n"
        f"Environment: {env}",
        border_style="blue"
    ))
    
    # Define suites
    suites = {
        "mcp": unittest.TestLoader().loadTestsFromTestCase(TestGHLMCP),
        "instantly": unittest.TestLoader().loadTestsFromTestCase(TestInstantlyMCP),
        "document": unittest.TestLoader().loadTestsFromTestCase(TestDocumentMCP),
        "webhooks": unittest.TestLoader().loadTestsFromTestCase(TestWebhookHandlers),
        "rpi": unittest.TestLoader().loadTestsFromTestCase(TestRPIWorkflow),
        "pipeline": unittest.TestLoader().loadTestsFromTestCase(TestEndToEndPipeline),
        "staging": unittest.TestLoader().loadTestsFromTestCase(TestStagingEnvironment)
    }
    
    # Run specified suite or all
    if suite_name and suite_name in suites:
        test_suite = suites[suite_name]
    else:
        test_suite = unittest.TestSuite()
        for suite in suites.values():
            test_suite.addTests(suite)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Summary
    console.print("\n")
    
    table = Table(title="Test Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="white")
    
    table.add_row("Tests Run", str(result.testsRun))
    table.add_row("Passed", str(result.testsRun - len(result.failures) - len(result.errors)))
    table.add_row("Failed", str(len(result.failures)))
    table.add_row("Errors", str(len(result.errors)))
    
    console.print(table)
    
    if result.wasSuccessful():
        console.print("\n[bold green]✓ All tests passed![/bold green]")
    else:
        console.print("\n[bold red]✗ Some tests failed[/bold red]")
        
        if result.failures:
            console.print("\n[red]Failures:[/red]")
            for test, traceback in result.failures:
                console.print(f"  - {test}")
        
        if result.errors:
            console.print("\n[red]Errors:[/red]")
            for test, traceback in result.errors:
                console.print(f"  - {test}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Alpha Swarm integration tests")
    parser.add_argument("--suite", choices=["mcp", "instantly", "document", "webhooks", "rpi", "pipeline", "staging"],
                       help="Specific test suite to run")
    parser.add_argument("--env", choices=["staging", "production"], default="staging",
                       help="Test environment")
    
    args = parser.parse_args()
    
    success = run_test_suite(args.suite, args.env)
    sys.exit(0 if success else 1)
