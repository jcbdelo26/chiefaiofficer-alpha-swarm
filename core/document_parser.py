#!/usr/bin/env python3
"""
Document Parser Module
======================

Agentic Document Extraction (ADE) capabilities for the Alpha Swarm.
Based on DeepLearning.AI + LandingAI methodology.

This module provides:
- PDF to Markdown conversion with layout preservation
- Image document processing with OCR
- Visual grounding with bounding boxes
- Schema-based field extraction

Usage:
    from core.document_parser import DocumentParser, parse_document
    
    parser = DocumentParser()
    result = parser.parse_pdf("company_report.pdf")
    print(result.markdown)
"""

import os
import sys
import json
import base64
import hashlib
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum
import re

# Add project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel

console = Console()


class DocumentType(Enum):
    """Supported document types."""
    PDF = "pdf"
    IMAGE = "image"
    SCAN = "scan"
    FORM = "form"
    TABLE = "table"


class ExtractionConfidence(Enum):
    """Confidence levels for extracted data."""
    HIGH = "high"       # >90% confidence
    MEDIUM = "medium"   # 70-90% confidence
    LOW = "low"         # <70% confidence
    UNVERIFIED = "unverified"


@dataclass
class BoundingBox:
    """Visual grounding bounding box."""
    x: float        # Left coordinate (0-1 normalized)
    y: float        # Top coordinate (0-1 normalized)
    width: float    # Width (0-1 normalized)
    height: float   # Height (0-1 normalized)
    page: int = 1   # Page number (1-indexed)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_css(self, scale: float = 100) -> str:
        """Convert to CSS positioning."""
        return f"left: {self.x * scale}%; top: {self.y * scale}%; width: {self.width * scale}%; height: {self.height * scale}%;"


@dataclass
class ExtractedRegion:
    """A region extracted from a document."""
    region_id: str
    region_type: str  # text, table, chart, image, form_field
    content: str      # Extracted text or structured content
    bounding_box: Optional[BoundingBox] = None
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.bounding_box:
            data['bounding_box'] = self.bounding_box.to_dict()
        return data


@dataclass
class ExtractedField:
    """A key-value field extracted from a document."""
    field_name: str
    field_value: Any
    field_type: str  # string, number, date, list, etc.
    source_region: Optional[str] = None  # region_id reference
    bounding_box: Optional[BoundingBox] = None
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.bounding_box:
            data['bounding_box'] = self.bounding_box.to_dict()
        return data


@dataclass
class ParsedDocument:
    """Complete parsed document result."""
    document_id: str
    source_path: str
    document_type: str
    page_count: int
    
    # Extracted content
    markdown: str                          # Full document as Markdown
    regions: List[ExtractedRegion]         # Individual regions
    extracted_fields: List[ExtractedField] # Schema-based extractions
    
    # Metadata
    parsed_at: str
    parse_duration_ms: int
    overall_confidence: float
    warnings: List[str] = field(default_factory=list)
    
    # For RAG integration
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_path": self.source_path,
            "document_type": self.document_type,
            "page_count": self.page_count,
            "markdown": self.markdown,
            "regions": [r.to_dict() for r in self.regions],
            "extracted_fields": [f.to_dict() for f in self.extracted_fields],
            "parsed_at": self.parsed_at,
            "parse_duration_ms": self.parse_duration_ms,
            "overall_confidence": self.overall_confidence,
            "warnings": self.warnings,
            "chunks": self.chunks
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    def get_field(self, field_name: str) -> Optional[Any]:
        """Get extracted field value by name."""
        for f in self.extracted_fields:
            if f.field_name == field_name:
                return f.field_value
        return None


# ============================================================================
# Extraction Schemas for Revenue Operations
# ============================================================================

LEAD_ENRICHMENT_SCHEMA = {
    "company_name": {"type": "string", "required": True},
    "employee_count": {"type": "number", "aliases": ["headcount", "team size", "employees"]},
    "annual_revenue": {"type": "string", "aliases": ["revenue", "ARR", "MRR"]},
    "industry": {"type": "string"},
    "tech_stack": {"type": "list", "aliases": ["technologies", "tools", "platforms"]},
    "funding_stage": {"type": "string", "aliases": ["series", "funding", "investment"]},
    "pain_points": {"type": "list", "aliases": ["challenges", "problems", "issues"]},
    "key_contacts": {"type": "list", "aliases": ["executives", "leadership", "team"]},
    "competitive_info": {"type": "list", "aliases": ["competitors", "alternatives"]},
}

COMPETITIVE_INTEL_SCHEMA = {
    "company_name": {"type": "string", "required": True},
    "product_name": {"type": "string"},
    "pricing": {"type": "string", "aliases": ["cost", "price", "plans"]},
    "features": {"type": "list", "aliases": ["capabilities", "offerings"]},
    "weaknesses": {"type": "list", "aliases": ["limitations", "drawbacks"]},
    "target_market": {"type": "string", "aliases": ["customers", "segments"]},
}

EVENT_MATERIALS_SCHEMA = {
    "event_name": {"type": "string", "required": True},
    "event_date": {"type": "date"},
    "speakers": {"type": "list"},
    "topics": {"type": "list", "aliases": ["sessions", "tracks"]},
    "sponsors": {"type": "list"},
    "attendee_info": {"type": "string"},
}


class DocumentParser:
    """
    Agentic Document Parser for Revenue Operations.
    
    Uses iterative extraction pattern:
    1. Layout Detection - Identify regions (tables, text, images)
    2. Reading Order - Sort regions logically
    3. Extraction - Use VLM/OCR to extract content
    4. Validation - Verify with bounding boxes
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / ".hive-mind" / "parsed_documents"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Cropped visuals for grounding
        self.visuals_dir = self.output_dir / "cropped_visuals"
        self.visuals_dir.mkdir(parents=True, exist_ok=True)
        
        # OCR engine (will be initialized on first use)
        self._ocr_engine = None
        self._pdf_engine = None
    
    def _get_document_id(self, path: Path) -> str:
        """Generate unique document ID."""
        content_hash = hashlib.md5(path.name.encode()).hexdigest()[:8]
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"doc_{content_hash}_{timestamp}"
    
    def _detect_document_type(self, path: Path) -> DocumentType:
        """Detect document type from file."""
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return DocumentType.PDF
        elif suffix in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
            return DocumentType.IMAGE
        elif suffix in [".tiff", ".tif"]:
            return DocumentType.SCAN
        else:
            return DocumentType.PDF  # Default
    
    def parse_pdf(
        self, 
        path: Path,
        schema: Optional[Dict] = None,
        max_pages: int = 20
    ) -> ParsedDocument:
        """
        Parse a PDF document using agentic extraction.
        
        Args:
            path: Path to PDF file
            schema: Optional extraction schema for structured fields
            max_pages: Maximum pages to process
            
        Returns:
            ParsedDocument with extracted content
        """
        import time
        start_time = time.time()
        
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Document not found: {path}")
        
        console.print(f"[dim]Parsing PDF: {path.name}[/dim]")
        
        document_id = self._get_document_id(path)
        regions = []
        warnings = []
        
        # Try to use PyMuPDF (fitz) for PDF extraction
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(path)
            page_count = min(len(doc), max_pages)
            
            full_text = []
            
            for page_num in range(page_count):
                page = doc[page_num]
                
                # Extract text with layout preservation
                text = page.get_text("text")
                full_text.append(f"## Page {page_num + 1}\n\n{text}")
                
                # Extract text blocks with bounding boxes
                blocks = page.get_text("dict")["blocks"]
                for i, block in enumerate(blocks):
                    if block.get("type") == 0:  # Text block
                        lines = []
                        for line in block.get("lines", []):
                            spans_text = " ".join(span.get("text", "") for span in line.get("spans", []))
                            lines.append(spans_text)
                        
                        content = "\n".join(lines)
                        if content.strip():
                            # Normalize bounding box to 0-1
                            bbox = block.get("bbox", [0, 0, 100, 100])
                            page_rect = page.rect
                            
                            regions.append(ExtractedRegion(
                                region_id=f"page{page_num+1}_block{i}",
                                region_type="text",
                                content=content,
                                bounding_box=BoundingBox(
                                    x=bbox[0] / page_rect.width,
                                    y=bbox[1] / page_rect.height,
                                    width=(bbox[2] - bbox[0]) / page_rect.width,
                                    height=(bbox[3] - bbox[1]) / page_rect.height,
                                    page=page_num + 1
                                ),
                                confidence=0.85
                            ))
                
                # Extract tables
                tables = page.find_tables()
                for j, table in enumerate(tables):
                    table_data = table.extract()
                    if table_data:
                        # Convert to Markdown table
                        md_table = self._table_to_markdown(table_data)
                        regions.append(ExtractedRegion(
                            region_id=f"page{page_num+1}_table{j}",
                            region_type="table",
                            content=md_table,
                            bounding_box=BoundingBox(
                                x=table.bbox[0] / page.rect.width,
                                y=table.bbox[1] / page.rect.height,
                                width=(table.bbox[2] - table.bbox[0]) / page.rect.width,
                                height=(table.bbox[3] - table.bbox[1]) / page.rect.height,
                                page=page_num + 1
                            ),
                            confidence=0.80,
                            metadata={"rows": len(table_data), "cols": len(table_data[0]) if table_data else 0}
                        ))
            
            doc.close()
            markdown = "\n\n".join(full_text)
            
        except ImportError:
            warnings.append("PyMuPDF not installed - using basic text extraction")
            markdown = self._basic_pdf_extract(path)
            page_count = 1
        
        # Extract structured fields if schema provided
        extracted_fields = []
        if schema:
            extracted_fields = self._extract_fields_from_text(markdown, schema)
        
        # Generate chunks for RAG
        chunks = self._generate_chunks(markdown, regions)
        
        # Calculate overall confidence
        if regions:
            overall_confidence = sum(r.confidence for r in regions) / len(regions)
        else:
            overall_confidence = 0.5
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        result = ParsedDocument(
            document_id=document_id,
            source_path=str(path),
            document_type=DocumentType.PDF.value,
            page_count=page_count,
            markdown=markdown,
            regions=regions,
            extracted_fields=extracted_fields,
            parsed_at=datetime.utcnow().isoformat(),
            parse_duration_ms=duration_ms,
            overall_confidence=overall_confidence,
            warnings=warnings,
            chunks=chunks
        )
        
        # Save parsed result
        output_path = self.output_dir / f"{document_id}.json"
        with open(output_path, "w") as f:
            f.write(result.to_json())
        
        console.print(f"[green]✓[/green] Parsed {page_count} pages, {len(regions)} regions, {len(extracted_fields)} fields")
        
        return result
    
    def parse_image(
        self,
        path: Path,
        schema: Optional[Dict] = None
    ) -> ParsedDocument:
        """
        Parse an image document using OCR.
        
        Args:
            path: Path to image file
            schema: Optional extraction schema
            
        Returns:
            ParsedDocument with extracted content
        """
        import time
        start_time = time.time()
        
        path = Path(path)
        document_id = self._get_document_id(path)
        warnings = []
        regions = []
        
        console.print(f"[dim]Parsing image: {path.name}[/dim]")
        
        try:
            # Try PaddleOCR first (as recommended in the course)
            from paddleocr import PaddleOCR
            
            if self._ocr_engine is None:
                self._ocr_engine = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
            
            result = self._ocr_engine.ocr(str(path), cls=True)
            
            lines = []
            for line in result[0]:
                bbox, (text, confidence) = line
                lines.append(text)
                
                # Convert bbox to normalized format
                # PaddleOCR returns [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                x1, y1 = bbox[0]
                x2, y2 = bbox[2]
                
                # We'd need image dimensions to normalize - estimate
                regions.append(ExtractedRegion(
                    region_id=f"ocr_{len(regions)}",
                    region_type="text",
                    content=text,
                    bounding_box=None,  # Would need image size to normalize
                    confidence=confidence
                ))
            
            markdown = "\n".join(lines)
            
        except ImportError:
            warnings.append("PaddleOCR not installed - using basic extraction")
            # Fallback to pytesseract
            try:
                import pytesseract
                from PIL import Image
                
                img = Image.open(path)
                markdown = pytesseract.image_to_string(img)
                
            except ImportError:
                warnings.append("No OCR engine available")
                markdown = f"[Image: {path.name} - OCR not available]"
        
        # Extract fields if schema provided
        extracted_fields = []
        if schema:
            extracted_fields = self._extract_fields_from_text(markdown, schema)
        
        chunks = self._generate_chunks(markdown, regions)
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        return ParsedDocument(
            document_id=document_id,
            source_path=str(path),
            document_type=DocumentType.IMAGE.value,
            page_count=1,
            markdown=markdown,
            regions=regions,
            extracted_fields=extracted_fields,
            parsed_at=datetime.utcnow().isoformat(),
            parse_duration_ms=duration_ms,
            overall_confidence=0.75 if regions else 0.5,
            warnings=warnings,
            chunks=chunks
        )
    
    def _table_to_markdown(self, table_data: List[List]) -> str:
        """Convert table data to Markdown format."""
        if not table_data:
            return ""
        
        lines = []
        
        # Header row
        header = table_data[0]
        lines.append("| " + " | ".join(str(cell or "") for cell in header) + " |")
        lines.append("| " + " | ".join("---" for _ in header) + " |")
        
        # Data rows
        for row in table_data[1:]:
            lines.append("| " + " | ".join(str(cell or "") for cell in row) + " |")
        
        return "\n".join(lines)
    
    def _basic_pdf_extract(self, path: Path) -> str:
        """Basic PDF text extraction fallback."""
        try:
            import pypdf
            reader = pypdf.PdfReader(path)
            text = []
            for page in reader.pages:
                text.append(page.extract_text())
            return "\n\n".join(text)
        except ImportError:
            return f"[PDF: {path.name} - extraction library not available]"
    
    def _extract_fields_from_text(
        self,
        text: str,
        schema: Dict[str, Dict]
    ) -> List[ExtractedField]:
        """
        Extract structured fields from text using pattern matching.
        For production, this would use a VLM or fine-tuned model.
        """
        extracted = []
        text_lower = text.lower()
        
        for field_name, field_config in schema.items():
            field_type = field_config.get("type", "string")
            aliases = field_config.get("aliases", [])
            search_terms = [field_name.replace("_", " ")] + aliases
            
            value = None
            confidence = 0.0
            
            for term in search_terms:
                # Simple pattern: "term: value" or "term value"
                patterns = [
                    rf"{term}[:\s]+([^\n,]+)",
                    rf"([^\n,]+)\s+{term}",
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, text_lower, re.IGNORECASE)
                    if match:
                        raw_value = match.group(1).strip()
                        
                        # Type conversion
                        if field_type == "number":
                            numbers = re.findall(r'[\d,]+', raw_value)
                            if numbers:
                                value = int(numbers[0].replace(",", ""))
                                confidence = 0.7
                        elif field_type == "list":
                            value = [v.strip() for v in raw_value.split(",")]
                            confidence = 0.6
                        else:
                            value = raw_value[:100]  # Truncate long values
                            confidence = 0.65
                        
                        break
                
                if value:
                    break
            
            if value:
                extracted.append(ExtractedField(
                    field_name=field_name,
                    field_value=value,
                    field_type=field_type,
                    confidence=confidence
                ))
        
        return extracted
    
    def _generate_chunks(
        self,
        markdown: str,
        regions: List[ExtractedRegion],
        chunk_size: int = 500
    ) -> List[Dict[str, Any]]:
        """Generate chunks for RAG embedding."""
        chunks = []
        
        # Simple chunking by paragraphs
        paragraphs = markdown.split("\n\n")
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) < chunk_size:
                current_chunk += "\n\n" + para
            else:
                if current_chunk.strip():
                    chunks.append({
                        "chunk_id": f"chunk_{len(chunks)}",
                        "content": current_chunk.strip(),
                        "char_count": len(current_chunk),
                        "type": "text"
                    })
                current_chunk = para
        
        # Add final chunk
        if current_chunk.strip():
            chunks.append({
                "chunk_id": f"chunk_{len(chunks)}",
                "content": current_chunk.strip(),
                "char_count": len(current_chunk),
                "type": "text"
            })
        
        # Add table regions as separate chunks
        for region in regions:
            if region.region_type == "table":
                chunks.append({
                    "chunk_id": region.region_id,
                    "content": region.content,
                    "char_count": len(region.content),
                    "type": "table",
                    "bounding_box": region.bounding_box.to_dict() if region.bounding_box else None
                })
        
        return chunks


# ============================================================================
# Convenience Functions
# ============================================================================

def parse_document(
    path: str | Path,
    schema: Optional[Dict] = None
) -> ParsedDocument:
    """
    Parse any supported document type.
    
    Args:
        path: Path to document
        schema: Optional extraction schema
        
    Returns:
        ParsedDocument result
    """
    parser = DocumentParser()
    path = Path(path)
    
    if path.suffix.lower() == ".pdf":
        return parser.parse_pdf(path, schema)
    else:
        return parser.parse_image(path, schema)


def parse_for_lead_enrichment(path: str | Path) -> ParsedDocument:
    """Parse document for lead enrichment data."""
    return parse_document(path, LEAD_ENRICHMENT_SCHEMA)


def parse_for_competitive_intel(path: str | Path) -> ParsedDocument:
    """Parse document for competitive intelligence."""
    return parse_document(path, COMPETITIVE_INTEL_SCHEMA)


def parse_for_event_materials(path: str | Path) -> ParsedDocument:
    """Parse event materials (brochures, agendas)."""
    return parse_document(path, EVENT_MATERIALS_SCHEMA)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    arg_parser = argparse.ArgumentParser(description="Parse documents for Alpha Swarm")
    arg_parser.add_argument("--input", "-i", type=Path, required=True, help="Document to parse")
    arg_parser.add_argument("--schema", "-s", choices=["lead", "competitive", "event"], help="Extraction schema")
    arg_parser.add_argument("--output", "-o", type=Path, help="Output JSON path")
    
    args = arg_parser.parse_args()
    
    schema = None
    if args.schema == "lead":
        schema = LEAD_ENRICHMENT_SCHEMA
    elif args.schema == "competitive":
        schema = COMPETITIVE_INTEL_SCHEMA
    elif args.schema == "event":
        schema = EVENT_MATERIALS_SCHEMA
    
    result = parse_document(args.input, schema)
    
    console.print(Panel.fit(
        f"[bold green]Document Parsed Successfully[/bold green]\n\n"
        f"Document ID: {result.document_id}\n"
        f"Pages: {result.page_count}\n"
        f"Regions: {len(result.regions)}\n"
        f"Extracted Fields: {len(result.extracted_fields)}\n"
        f"Confidence: {result.overall_confidence:.0%}",
        border_style="green"
    ))
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(result.to_json())
        console.print(f"[green]✓[/green] Saved to {args.output}")
    
    # Print extracted fields
    if result.extracted_fields:
        console.print("\n[bold]Extracted Fields:[/bold]")
        for field in result.extracted_fields:
            console.print(f"  {field.field_name}: {field.field_value} ({field.confidence:.0%})")
