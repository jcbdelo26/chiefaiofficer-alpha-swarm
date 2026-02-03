#!/usr/bin/env python3
"""
Document-Based Lead Enricher
=============================

Enriches leads using Agentic Document Extraction (ADE) to parse:
- Company PDFs (annual reports, one-pagers, pitch decks)
- LinkedIn profile screenshots
- Event materials and collateral
- Competitive intelligence documents

This extends the standard Clay waterfall enrichment with document-based data.

Usage:
    python execution/enricher_document_ai.py --lead lead.json --documents ./docs/
    python execution/enricher_document_ai.py --batch leads.json --documents ./docs/
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress

from core.document_parser import (
    DocumentParser,
    ParsedDocument,
    LEAD_ENRICHMENT_SCHEMA,
    COMPETITIVE_INTEL_SCHEMA
)
from core.semantic_anchor import (
    attach_anchor,
    AnchorType,
    create_enrichment_anchor
)
from core.context import estimate_tokens, get_context_zone, ContextZone

console = Console()


@dataclass
class DocumentEnrichmentResult:
    """Result of document-based enrichment."""
    lead_id: str
    documents_processed: int
    fields_extracted: int
    enrichment_data: Dict[str, Any]
    confidence_score: float
    source_documents: List[str]
    visual_references: List[Dict[str, Any]]  # Bounding box grounded data
    warnings: List[str] = field(default_factory=list)


class DocumentEnricher:
    """
    Enriches leads using document analysis.
    
    Implements the agentic extraction pattern:
    1. Identify relevant documents for each lead
    2. Parse documents with appropriate schema
    3. Match extracted data to lead fields
    4. Attach semantic anchors with visual grounding
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.parser = DocumentParser()
        self.output_dir = output_dir or Path(__file__).parent.parent / ".hive-mind" / "enriched_docs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def enrich_lead(
        self,
        lead: Dict[str, Any],
        documents_dir: Path,
        schema: Optional[Dict] = None
    ) -> DocumentEnrichmentResult:
        """
        Enrich a single lead using documents in the specified directory.
        
        Args:
            lead: Lead data dictionary
            documents_dir: Directory containing documents to parse
            schema: Extraction schema (defaults to LEAD_ENRICHMENT_SCHEMA)
            
        Returns:
            DocumentEnrichmentResult with extracted data
        """
        lead_id = lead.get("lead_id", "unknown")
        company_name = lead.get("company", lead.get("company_name", ""))
        
        console.print(f"[dim]Enriching lead {lead_id} from documents...[/dim]")
        
        schema = schema or LEAD_ENRICHMENT_SCHEMA
        
        # Find matching documents
        matching_docs = self._find_matching_documents(
            documents_dir,
            company_name=company_name,
            lead_name=lead.get("name", "")
        )
        
        if not matching_docs:
            console.print(f"[yellow]  No matching documents found for {company_name}[/yellow]")
            return DocumentEnrichmentResult(
                lead_id=lead_id,
                documents_processed=0,
                fields_extracted=0,
                enrichment_data={},
                confidence_score=0.0,
                source_documents=[],
                visual_references=[],
                warnings=["No matching documents found"]
            )
        
        # Parse all matching documents
        parsed_docs = []
        for doc_path in matching_docs:
            try:
                parsed = self.parser.parse_pdf(doc_path, schema) if doc_path.suffix.lower() == ".pdf" \
                    else self.parser.parse_image(doc_path, schema)
                parsed_docs.append(parsed)
            except Exception as e:
                console.print(f"[red]  Error parsing {doc_path.name}: {e}[/red]")
        
        # Merge extracted fields from all documents
        merged_data = self._merge_extracted_fields(parsed_docs)
        
        # Collect visual references for grounding
        visual_refs = self._collect_visual_references(parsed_docs)
        
        # Calculate overall confidence
        if parsed_docs:
            avg_confidence = sum(d.overall_confidence for d in parsed_docs) / len(parsed_docs)
        else:
            avg_confidence = 0.0
        
        return DocumentEnrichmentResult(
            lead_id=lead_id,
            documents_processed=len(parsed_docs),
            fields_extracted=len(merged_data),
            enrichment_data=merged_data,
            confidence_score=avg_confidence,
            source_documents=[str(d) for d in matching_docs],
            visual_references=visual_refs
        )
    
    def enrich_batch(
        self,
        leads: List[Dict[str, Any]],
        documents_dir: Path,
        schema: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Enrich a batch of leads with document data.
        
        Args:
            leads: List of lead dictionaries
            documents_dir: Directory containing documents
            schema: Extraction schema
            
        Returns:
            List of enriched leads
        """
        console.print(f"\n[bold blue]📄 DOCUMENT ENRICHER[/bold blue]")
        console.print(f"[dim]Processing {len(leads)} leads from {documents_dir}[/dim]\n")
        
        # Context zone check
        tokens = estimate_tokens(leads)
        zone = get_context_zone(tokens)
        if zone != ContextZone.SMART:
            console.print(f"[yellow]⚠️ Context zone: {zone.value} - Consider batching[/yellow]")
        
        enriched_leads = []
        
        with Progress() as progress:
            task = progress.add_task("Enriching leads...", total=len(leads))
            
            for lead in leads:
                result = self.enrich_lead(lead, documents_dir, schema)
                
                # Merge enrichment data into lead
                enriched_lead = lead.copy()
                
                if result.enrichment_data:
                    enriched_lead["document_enrichment"] = result.enrichment_data
                    enriched_lead["has_document_data"] = True
                    
                    # Update lead fields with higher confidence data
                    for field_name, value in result.enrichment_data.items():
                        if value and field_name in ["company_size", "employee_count"]:
                            if isinstance(value, (int, float)):
                                enriched_lead["company_size"] = int(value)
                        elif value and field_name == "industry":
                            enriched_lead["industry"] = value
                        elif value and field_name == "tech_stack":
                            if "personalization_hooks" not in enriched_lead:
                                enriched_lead["personalization_hooks"] = []
                            enriched_lead["personalization_hooks"].extend(value[:3])
                    
                    # Attach semantic anchor
                    enriched_lead = attach_anchor(
                        enriched_lead,
                        AnchorType.ENRICHMENT,
                        why=f"Documents provided additional context from {result.documents_processed} files",
                        what=f"Extracted {result.fields_extracted} fields with {result.confidence_score:.0%} confidence",
                        how="Agentic Document Extraction (ADE) with visual grounding",
                        created_by="ENRICHER_DOCUMENT_AI",
                        confidence=result.confidence_score,
                        metadata={
                            "source_documents": result.source_documents[:5],
                            "visual_references": result.visual_references[:3]
                        }
                    )
                
                enriched_leads.append(enriched_lead)
                progress.update(task, advance=1)
        
        # Summary
        docs_processed = sum(1 for l in enriched_leads if l.get("has_document_data"))
        console.print(f"\n[green]✓[/green] Enriched {docs_processed}/{len(leads)} leads with document data")
        
        return enriched_leads
    
    def _find_matching_documents(
        self,
        documents_dir: Path,
        company_name: str,
        lead_name: str
    ) -> List[Path]:
        """Find documents matching the lead's company or name."""
        if not documents_dir.exists():
            return []
        
        matching = []
        search_terms = [
            company_name.lower().replace(" ", "_"),
            company_name.lower().replace(" ", "-"),
            company_name.lower().split()[0] if company_name else "",
            lead_name.lower().replace(" ", "_"),
        ]
        search_terms = [t for t in search_terms if t]
        
        for doc in documents_dir.glob("*"):
            if doc.is_file() and doc.suffix.lower() in [".pdf", ".jpg", ".jpeg", ".png"]:
                doc_name_lower = doc.name.lower()
                for term in search_terms:
                    if term and term in doc_name_lower:
                        matching.append(doc)
                        break
        
        return matching
    
    def _merge_extracted_fields(
        self,
        parsed_docs: List[ParsedDocument]
    ) -> Dict[str, Any]:
        """Merge extracted fields from multiple documents."""
        merged = {}
        
        for doc in parsed_docs:
            for field in doc.extracted_fields:
                field_name = field.field_name
                
                # Keep highest confidence value
                if field_name not in merged or field.confidence > merged.get(f"{field_name}_confidence", 0):
                    merged[field_name] = field.field_value
                    merged[f"{field_name}_confidence"] = field.confidence
        
        # Clean up confidence keys for final output
        return {k: v for k, v in merged.items() if not k.endswith("_confidence")}
    
    def _collect_visual_references(
        self,
        parsed_docs: List[ParsedDocument]
    ) -> List[Dict[str, Any]]:
        """Collect visual references (bounding boxes) for grounding."""
        refs = []
        
        for doc in parsed_docs:
            for field in doc.extracted_fields:
                if field.bounding_box:
                    refs.append({
                        "field_name": field.field_name,
                        "value": field.field_value,
                        "document": doc.source_path,
                        "bounding_box": field.bounding_box.to_dict()
                    })
        
        return refs


def enrich_lead_from_documents(
    lead: Dict[str, Any],
    documents_dir: str | Path
) -> Dict[str, Any]:
    """
    Convenience function to enrich a single lead.
    
    Args:
        lead: Lead dictionary
        documents_dir: Path to documents directory
        
    Returns:
        Enriched lead dictionary
    """
    enricher = DocumentEnricher()
    result = enricher.enrich_lead(lead, Path(documents_dir))
    
    if result.enrichment_data:
        lead["document_enrichment"] = result.enrichment_data
        lead["has_document_data"] = True
    
    return lead


def main():
    parser = argparse.ArgumentParser(description="Enrich leads from documents")
    parser.add_argument("--lead", type=Path, help="Single lead JSON file")
    parser.add_argument("--batch", type=Path, help="Batch leads JSON file")
    parser.add_argument("--documents", type=Path, required=True, help="Documents directory")
    parser.add_argument("--output", type=Path, help="Output JSON path")
    parser.add_argument("--schema", choices=["lead", "competitive"], default="lead")
    
    args = parser.parse_args()
    
    schema = LEAD_ENRICHMENT_SCHEMA if args.schema == "lead" else COMPETITIVE_INTEL_SCHEMA
    enricher = DocumentEnricher()
    
    if args.lead:
        with open(args.lead) as f:
            lead = json.load(f)
        
        result = enricher.enrich_lead(lead, args.documents, schema)
        
        console.print(Panel.fit(
            f"[bold green]Lead Enriched[/bold green]\n\n"
            f"Lead ID: {result.lead_id}\n"
            f"Documents: {result.documents_processed}\n"
            f"Fields: {result.fields_extracted}\n"
            f"Confidence: {result.confidence_score:.0%}",
            border_style="green"
        ))
        
        if result.enrichment_data:
            console.print("\n[bold]Extracted Data:[/bold]")
            for k, v in result.enrichment_data.items():
                console.print(f"  {k}: {v}")
    
    elif args.batch:
        with open(args.batch) as f:
            data = json.load(f)
        
        leads = data.get("leads", data) if isinstance(data, dict) else data
        enriched = enricher.enrich_batch(leads, args.documents, schema)
        
        output = {
            "enriched_at": datetime.utcnow().isoformat(),
            "total_leads": len(enriched),
            "document_enriched": sum(1 for l in enriched if l.get("has_document_data")),
            "leads": enriched
        }
        
        if args.output:
            with open(args.output, "w") as f:
                json.dump(output, f, indent=2)
            console.print(f"\n[green]✓[/green] Saved to {args.output}")
        
        # Display summary table
        table = Table(title="Document Enrichment Results")
        table.add_column("Lead ID", style="cyan")
        table.add_column("Company", style="white")
        table.add_column("Doc Data", style="green")
        table.add_column("Fields", style="yellow")
        
        for lead in enriched[:10]:
            table.add_row(
                lead.get("lead_id", "")[:12],
                lead.get("company", "")[:20],
                "✓" if lead.get("has_document_data") else "-",
                str(len(lead.get("document_enrichment", {})))
            )
        
        console.print(table)


if __name__ == "__main__":
    main()
