#!/usr/bin/env python3
"""
DEPRECATED: This file is a backward-compatibility shim.

The enricher has been renamed from enricher_clay_waterfall to enricher_waterfall
because it does NOT use Clay's API — it uses Apollo.io + BetterContact waterfall.

All imports are re-exported from the new module for backward compatibility.
"""

# Re-export everything from the new module
from execution.enricher_waterfall import (  # noqa: F401
    WaterfallEnricher,
    WaterfallEnricher as ClayEnricher,  # backward-compat alias
    EnrichedContact,
    EnrichedCompany,
    IntentSignals,
    EnrichedLead,
    main,
)

if __name__ == "__main__":
    main()
