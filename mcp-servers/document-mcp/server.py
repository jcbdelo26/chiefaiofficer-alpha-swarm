#!/usr/bin/env python3
"""
Document Extraction MCP Server
==============================

Model Context Protocol (MCP) server for Agentic Document Extraction.
Exposes document parsing and enrichment capabilities as tools.

Tools Available:
- parse_document: Parse any PDF or image document
- enrich_lead_from_doc: Enrich a lead using document data
- extract_competitive_intel: Extract competitive intelligence from documents
- batch_parse_directory: Parse all documents in a directory

Usage:
    # Start MCP server
    python mcp-servers/document-mcp/server.py
    
    # Or with uvx
    uvx mcp-servers/document-mcp
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# Add project paths
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, Resource
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("MCP SDK not installed. Install with: pip install mcp")

from core.document_parser import (
    DocumentParser,
    parse_document,
    parse_for_lead_enrichment,
    parse_for_competitive_intel,
    LEAD_ENRICHMENT_SCHEMA,
    COMPETITIVE_INTEL_SCHEMA,
    EVENT_MATERIALS_SCHEMA
)
from execution.enricher_document_ai import DocumentEnricher


# Server metadata
SERVER_NAME = "document-extraction-mcp"
SERVER_VERSION = "1.0.0"


if MCP_AVAILABLE:
    # Initialize MCP server
    server = Server(SERVER_NAME)
    
    # Initialize our document tools
    parser = DocumentParser()
    enricher = DocumentEnricher()
    
    
    @server.list_tools()
    async def list_tools() -> List[Tool]:
        """List available document extraction tools."""
        return [
            Tool(
                name="parse_document",
                description="""Parse a document (PDF or image) and extract text, tables, and structured data.
                
                Returns:
                - Markdown representation of the document
                - Extracted regions with bounding boxes
                - Structured fields if schema is provided
                
                Supports: PDF, JPG, PNG, TIFF""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "document_path": {
                            "type": "string",
                            "description": "Path to the document file"
                        },
                        "schema_type": {
                            "type": "string",
                            "enum": ["lead", "competitive", "event", "none"],
                            "description": "Type of extraction schema to use",
                            "default": "none"
                        }
                    },
                    "required": ["document_path"]
                }
            ),
            Tool(
                name="enrich_lead_from_document",
                description="""Enrich a lead with data extracted from a document.
                
                Uses Agentic Document Extraction to find:
                - Company size, revenue, industry
                - Tech stack and tools used
                - Pain points and challenges
                - Key contacts
                
                Returns enriched lead data with semantic anchors.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "lead_json": {
                            "type": "string",
                            "description": "JSON string of the lead to enrich"
                        },
                        "document_path": {
                            "type": "string",
                            "description": "Path to document file"
                        }
                    },
                    "required": ["lead_json", "document_path"]
                }
            ),
            Tool(
                name="extract_competitive_intel",
                description="""Extract competitive intelligence from a document.
                
                Finds:
                - Competitor name and products
                - Pricing information
                - Feature lists
                - Weaknesses and limitations
                - Target market
                
                Useful for analyzing competitor collateral.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "document_path": {
                            "type": "string",
                            "description": "Path to competitor document"
                        }
                    },
                    "required": ["document_path"]
                }
            ),
            Tool(
                name="batch_parse_directory",
                description="""Parse all documents in a directory.
                
                Processes all PDF and image files, returning summaries.
                Useful for bulk document ingestion.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "directory_path": {
                            "type": "string",
                            "description": "Path to directory containing documents"
                        },
                        "schema_type": {
                            "type": "string",
                            "enum": ["lead", "competitive", "event", "none"],
                            "default": "none"
                        },
                        "max_documents": {
                            "type": "integer",
                            "description": "Maximum documents to process",
                            "default": 10
                        }
                    },
                    "required": ["directory_path"]
                }
            ),
            Tool(
                name="get_document_chunks",
                description="""Get RAG-ready chunks from a parsed document.
                
                Returns text chunks suitable for embedding and retrieval.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "description": "Document ID from a previous parse operation"
                        }
                    },
                    "required": ["document_id"]
                }
            )
        ]
    
    
    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle tool calls."""
        
        try:
            if name == "parse_document":
                return await _parse_document(arguments)
            elif name == "enrich_lead_from_document":
                return await _enrich_lead_from_document(arguments)
            elif name == "extract_competitive_intel":
                return await _extract_competitive_intel(arguments)
            elif name == "batch_parse_directory":
                return await _batch_parse_directory(arguments)
            elif name == "get_document_chunks":
                return await _get_document_chunks(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
        
        except Exception as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    
    async def _parse_document(args: Dict[str, Any]) -> List[TextContent]:
        """Parse a document."""
        path = Path(args["document_path"])
        schema_type = args.get("schema_type", "none")
        
        schema = None
        if schema_type == "lead":
            schema = LEAD_ENRICHMENT_SCHEMA
        elif schema_type == "competitive":
            schema = COMPETITIVE_INTEL_SCHEMA
        elif schema_type == "event":
            schema = EVENT_MATERIALS_SCHEMA
        
        result = parse_document(path, schema)
        
        # Format response
        response = {
            "document_id": result.document_id,
            "source": str(path),
            "pages": result.page_count,
            "regions": len(result.regions),
            "confidence": result.overall_confidence,
            "markdown_preview": result.markdown[:2000] + "..." if len(result.markdown) > 2000 else result.markdown,
            "extracted_fields": [
                {"name": f.field_name, "value": f.field_value, "confidence": f.confidence}
                for f in result.extracted_fields
            ],
            "warnings": result.warnings
        }
        
        return [TextContent(type="text", text=json.dumps(response, indent=2))]
    
    
    async def _enrich_lead_from_document(args: Dict[str, Any]) -> List[TextContent]:
        """Enrich a lead with document data."""
        lead = json.loads(args["lead_json"])
        doc_path = Path(args["document_path"])
        
        # Parse the document
        parsed = parse_for_lead_enrichment(doc_path)
        
        # Merge into lead
        if parsed.extracted_fields:
            lead["document_enrichment"] = {
                f.field_name: f.field_value
                for f in parsed.extracted_fields
            }
            lead["has_document_data"] = True
            lead["document_source"] = str(doc_path)
            lead["document_confidence"] = parsed.overall_confidence
        
        return [TextContent(type="text", text=json.dumps(lead, indent=2))]
    
    
    async def _extract_competitive_intel(args: Dict[str, Any]) -> List[TextContent]:
        """Extract competitive intelligence."""
        path = Path(args["document_path"])
        
        result = parse_for_competitive_intel(path)
        
        intel = {
            "source_document": str(path),
            "parsed_at": result.parsed_at,
            "confidence": result.overall_confidence,
            "intelligence": {
                f.field_name: f.field_value
                for f in result.extracted_fields
            },
            "full_text_preview": result.markdown[:1500] + "..."
        }
        
        return [TextContent(type="text", text=json.dumps(intel, indent=2))]
    
    
    async def _batch_parse_directory(args: Dict[str, Any]) -> List[TextContent]:
        """Parse all documents in a directory."""
        dir_path = Path(args["directory_path"])
        schema_type = args.get("schema_type", "none")
        max_docs = args.get("max_documents", 10)
        
        schema = None
        if schema_type == "lead":
            schema = LEAD_ENRICHMENT_SCHEMA
        elif schema_type == "competitive":
            schema = COMPETITIVE_INTEL_SCHEMA
        
        results = []
        count = 0
        
        for doc in dir_path.glob("*"):
            if count >= max_docs:
                break
            
            if doc.suffix.lower() in [".pdf", ".jpg", ".jpeg", ".png"]:
                try:
                    parsed = parse_document(doc, schema)
                    results.append({
                        "document_id": parsed.document_id,
                        "file": doc.name,
                        "pages": parsed.page_count,
                        "fields_extracted": len(parsed.extracted_fields),
                        "confidence": parsed.overall_confidence
                    })
                    count += 1
                except Exception as e:
                    results.append({
                        "file": doc.name,
                        "error": str(e)
                    })
        
        return [TextContent(type="text", text=json.dumps({
            "directory": str(dir_path),
            "documents_processed": len(results),
            "results": results
        }, indent=2))]
    
    
    async def _get_document_chunks(args: Dict[str, Any]) -> List[TextContent]:
        """Get chunks from a parsed document."""
        doc_id = args["document_id"]
        
        # Load from parsed documents directory
        parsed_dir = project_root / ".hive-mind" / "parsed_documents"
        doc_file = parsed_dir / f"{doc_id}.json"
        
        if not doc_file.exists():
            return [TextContent(type="text", text=f"Document not found: {doc_id}")]
        
        with open(doc_file) as f:
            doc_data = json.load(f)
        
        chunks = doc_data.get("chunks", [])
        
        return [TextContent(type="text", text=json.dumps({
            "document_id": doc_id,
            "total_chunks": len(chunks),
            "chunks": chunks[:20]  # Limit to 20 chunks
        }, indent=2))]


# CLI for testing without MCP
def cli_mode():
    """Run in CLI mode for testing."""
    import argparse
    
    arg_parser = argparse.ArgumentParser(description="Document MCP Server CLI")
    arg_parser.add_argument("--parse", type=Path, help="Parse a document")
    arg_parser.add_argument("--schema", choices=["lead", "competitive", "event"])
    
    args = arg_parser.parse_args()
    
    if args.parse:
        schema = None
        if args.schema == "lead":
            schema = LEAD_ENRICHMENT_SCHEMA
        elif args.schema == "competitive":
            schema = COMPETITIVE_INTEL_SCHEMA
        elif args.schema == "event":
            schema = EVENT_MATERIALS_SCHEMA
        
        result = parse_document(args.parse, schema)
        
        print(f"\n📄 Document: {args.parse.name}")
        print(f"   Pages: {result.page_count}")
        print(f"   Regions: {len(result.regions)}")
        print(f"   Fields: {len(result.extracted_fields)}")
        print(f"   Confidence: {result.overall_confidence:.0%}")
        
        if result.extracted_fields:
            print("\n📋 Extracted Fields:")
            for f in result.extracted_fields:
                print(f"   {f.field_name}: {f.field_value}")


async def main():
    """Run the MCP server."""
    if not MCP_AVAILABLE:
        print("Running in CLI mode (MCP SDK not installed)")
        cli_mode()
        return
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    if MCP_AVAILABLE and len(sys.argv) == 1:
        import asyncio
        asyncio.run(main())
    else:
        cli_mode()
