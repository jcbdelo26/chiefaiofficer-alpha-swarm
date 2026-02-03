# 📄 Agentic Document Extraction (ADE) - Implementation Status

> From Andrew Ng's DeepLearning.AI Course to Production Implementation

**Source**: [Document AI: From OCR to Agentic Doc Extraction](https://www.deeplearning.ai/short-courses/document-ai-from-ocr-to-agentic-doc-extraction/)  
**Creator**: DeepLearning.AI + LandingAI (David Park, Andrea Kropp)  
**Discovered**: [Facebook Reel by Andrew Ng](https://www.facebook.com/reel/885409577529086)  
**Implemented**: 2026-01-15

---

## ✅ Implementation Complete

All planned document extraction capabilities have been implemented and integrated into the Alpha Swarm system.

| Component | File | Status |
|-----------|------|--------|
| Core Document Parser | `core/document_parser.py` | ✅ Complete |
| Document Enricher | `execution/enricher_document_ai.py` | ✅ Complete |
| MCP Server | `mcp-servers/document-mcp/server.py` | ✅ Complete |
| Extraction Schemas | `config/ade_schemas.yaml` | ✅ Complete |
| Executive Summary | `docs/EXECUTIVE_SUMMARY.md` | ✅ Complete |

---

## 📋 What Was Implemented

### 1. Core Document Parser (`core/document_parser.py`)

A comprehensive document parsing module that implements the ADE methodology:

```python
from core.document_parser import parse_document, parse_for_lead_enrichment

# Parse any document
result = parse_document("company_report.pdf", schema=LEAD_ENRICHMENT_SCHEMA)
print(result.markdown)  # Full text as Markdown
print(result.extracted_fields)  # Structured fields
print(result.regions)  # Text regions with bounding boxes
```

**Features**:
- ✅ PDF parsing with PyMuPDF (layout-aware)
- ✅ OCR for images (PaddleOCR primary, Tesseract fallback)
- ✅ Table extraction with Markdown output
- ✅ Bounding box visual grounding
- ✅ Schema-based field extraction
- ✅ RAG-ready chunk generation
- ✅ Confidence scoring

### 2. Document Enricher (`execution/enricher_document_ai.py`)

Extends lead enrichment with document data:

```bash
# Enrich a batch of leads with documents
python execution/enricher_document_ai.py \
    --batch .hive-mind/enriched/latest.json \
    --documents ./lead_documents/ \
    --output .hive-mind/enriched/doc_enriched.json
```

**Capabilities**:
- ✅ Match documents to leads by company name
- ✅ Merge extracted fields into lead data
- ✅ Attach semantic anchors with document source
- ✅ Visual reference tracking for grounding
- ✅ Context zone monitoring during batch processing

### 3. MCP Server (`mcp-servers/document-mcp/server.py`)

Exposes document extraction as MCP tools:

| Tool | Description |
|------|-------------|
| `parse_document` | Parse any PDF/image to structured data |
| `enrich_lead_from_document` | Add document data to a lead |
| `extract_competitive_intel` | Extract competitor information |
| `batch_parse_directory` | Process all documents in a folder |
| `get_document_chunks` | Get RAG-ready chunks |

```bash
# Start MCP server
python mcp-servers/document-mcp/server.py

# Or test in CLI mode
python mcp-servers/document-mcp/server.py --parse ./docs/report.pdf
```

### 4. Extraction Schemas (`config/ade_schemas.yaml`)

Pre-defined schemas for different document types:

| Schema | Use Case | Key Fields |
|--------|----------|------------|
| `lead_enrichment` | Company docs, pitch decks | employee_count, revenue, tech_stack, pain_points |
| `competitive_intel` | Competitor collateral | pricing, features, weaknesses |
| `event_materials` | Conference brochures | speakers, topics, sponsors |
| `financial_documents` | Annual reports | revenue, growth, margins |
| `linkedin_profile` | Profile screenshots | title, skills, experience |

---

## 🔄 Daily Usage in Revenue Operations

### Morning Lead Processing

```bash
# Standard enrichment from Clay
python execution/enricher_clay_waterfall.py --input .hive-mind/scraped/latest.json

# ENHANCED: Add document-based enrichment
python execution/enricher_document_ai.py \
    --batch .hive-mind/enriched/latest.json \
    --documents ./lead_documents/
```

### Document Ingestion Workflow

```bash
# 1. When you receive company materials (PDFs, images)
#    Place them in ./lead_documents/<company_name>_*.pdf

# 2. Parse for immediate use
python core/document_parser.py -i ./lead_documents/techcorp_report.pdf --schema lead

# 3. Or batch process overnight
python mcp-servers/document-mcp/server.py --parse ./lead_documents/
```

### Competitive Intelligence

```bash
# Parse competitor collateral
python core/document_parser.py -i ./competitor_docs/gong_pricing.pdf --schema competitive

# Extract into .hive-mind/parsed_documents/
```

---

## 📊 Expected Impact

| Metric | Before ADE | After ADE | Improvement |
|--------|-----------|-----------|-------------|
| Lead Data Completeness | 60% | 85% | **+42%** |
| Research Accuracy | 75% | 90% | **+20%** |
| AE Trust in Automation | 70% | 90% | **+29%** |
| Personalization Options | 3-4 hooks | 6-8 hooks | **+100%** |

---

## 🏗️ Architecture Integration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LEAD PIPELINE                                   │
│                                                                             │
│   LinkedIn  →  HUNTER  →  ENRICHER (Clay)  →  ENRICHER (Docs)  →  SEGMENTOR │
│                              │                      │                        │
│                              ▼                      ▼                        │
│                         API Data              Document Data                  │
│                         (structured)          (unstructured→structured)      │
└─────────────────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │ Semantic Anchors │
                                    │ with Visual      │
                                    │ Grounding        │
                                    └─────────────────┘
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │ GATEKEEPER      │
                                    │ Shows document  │
                                    │ evidence in     │
                                    │ AE review       │
                                    └─────────────────┘
```

---

## 🔧 Dependencies

### Required (Install via pip)
```
PyMuPDF (fitz)      # PDF parsing
paddleocr           # Primary OCR
pytesseract         # Fallback OCR
Pillow              # Image handling
pyyaml              # Schema parsing
```

### Optional (For MCP Server)
```
mcp                 # MCP SDK
```

### Install Command
```bash
pip install PyMuPDF paddleocr pytesseract Pillow pyyaml mcp
```

---

## 🎓 Training on Revenue Operations Standards

### Schema Customization

Edit `config/ade_schemas.yaml` to add company-specific fields:

```yaml
lead_enrichment:
  # Add custom fields for your ICP
  deal_stage:
    type: string
    aliases:
      - pipeline stage
      - opportunity status
    description: "Current deal stage if mentioned"
```

### Learning Loop

1. **Parse documents** → Observe extracted fields
2. **Review accuracy** → Note false positives/negatives
3. **Update schemas** → Add aliases, adjust field types
4. **Re-test** → Verify improvements
5. **Document learnings** → Add to `.hive-mind/learnings.json`

---

## 📚 Key Insights from Andrew Ng's Reel

| Insight | Implementation |
|---------|----------------|
| "Traditional OCR loses the layout" | PyMuPDF extracts with bounding boxes |
| "Treat documents as images" | Image parsing with PaddleOCR |
| "Iterate to extract" | Multi-pass extraction with confidence |
| "Ground to bounding boxes" | BoundingBox dataclass in all extractions |
| "Output as Markdown/JSON" | All parsers output both formats |

---

## 🚀 Next Steps

### Short Term
- [ ] Add visual grounding display in GATEKEEPER dashboard
- [ ] Create LinkedIn profile image parser
- [ ] Add handwriting recognition for event signup sheets

### Medium Term
- [ ] AWS Lambda deployment for serverless parsing
- [ ] Integration with Bedrock Knowledge Base
- [ ] Strands Agents for document Q&A

### Long Term
- [ ] Fine-tune extraction models on company data
- [ ] Real-time document monitoring for new leads
- [ ] Automated competitive intelligence pipeline

---

## 📖 Course Recommendations

For full understanding of the methodology, take the DeepLearning.AI course:

**[Document AI: From OCR to Agentic Doc Extraction](https://www.deeplearning.ai/short-courses/document-ai-from-ocr-to-agentic-doc-extraction/)**

**Course Outline**:
1. Document Processing Basics
2. OCR Evolution (4 decades)
3. Layout Detection & Reading Order
4. Building Agentic Document Understanding
5. ADE Framework (LandingAI)
6. ADE for RAG Applications
7. AWS Deployment with Strands Agents

---

*Implementation based on DeepLearning.AI + LandingAI methodology, discovered via Andrew Ng's Facebook Reel*
