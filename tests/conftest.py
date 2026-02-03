"""Pytest configuration and fixtures for chiefaiofficer-alpha-swarm tests."""

import pytest
from tests.mocks import MockIntegrationGateway, get_mock_gateway


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests to avoid test pollution."""
    yield
    # Reset MultiLayerFailsafe singleton after each test
    try:
        from core.multi_layer_failsafe import MultiLayerFailsafe
        MultiLayerFailsafe._instance = None
    except ImportError:
        pass


@pytest.fixture
def mock_gateway():
    """Get a mock integration gateway for testing."""
    return get_mock_gateway()


@pytest.fixture
def mock_ghl():
    """Get a mock GoHighLevel adapter for testing."""
    from tests.mocks import MockGHLAdapter
    return MockGHLAdapter()


@pytest.fixture
def mock_calendar():
    """Get a mock Google Calendar adapter for testing."""
    from tests.mocks import MockGoogleCalendarAdapter
    return MockGoogleCalendarAdapter()


@pytest.fixture
def mock_supabase():
    """Get a mock Supabase adapter for testing."""
    from tests.mocks import MockSupabaseAdapter
    return MockSupabaseAdapter()


@pytest.fixture
def mock_clay():
    """Get a mock Clay adapter for testing."""
    from tests.mocks import MockClayAdapter
    return MockClayAdapter()
