# Email Threading MCP Server

Model Context Protocol server for email thread parsing and intent detection.

## Features

- **parse_thread**: Parse email threads from raw RFC 5322 or plain text format
- **extract_context**: Extract conversation context, topics, dates, times
- **detect_intent**: Classify email intent (scheduling, objection, interest, etc.)
- **maintain_thread**: Generate proper In-Reply-To and References headers
- **summarize_thread**: Generate concise thread summaries
- **extract_action_items**: Pull out action items from email text

## Intent Classification

The server can detect these intents:

| Intent | Example Triggers |
|--------|-----------------|
| `scheduling_request` | "Can we schedule a call", "What's your availability" |
| `scheduling_confirm` | "Confirmed for", "See you on" |
| `scheduling_reschedule` | "Need to reschedule", "Can we move" |
| `scheduling_cancel` | "Need to cancel", "Can't make it" |
| `interest_high` | "Very interested", "Exactly what we need" |
| `interest_medium` | "Tell me more", "Sounds interesting" |
| `objection` | "Too expensive", "Not the right time" |
| `not_interested` | "Not interested", "Please remove me" |
| `out_of_office` | "Out of office", "On vacation" |
| `question` | Questions about product/service |
| `referral` | "Talk to my colleague", "Looping in" |

## Usage

### With Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "email-threading-mcp": {
      "command": "python",
      "args": ["mcp-servers/email-threading-mcp/server.py"]
    }
  }
}
```

### Programmatic Usage

```python
from mcp_servers.email_threading_mcp import EmailThreadingMCP

server = EmailThreadingMCP()

# Detect intent
result = server.detect_intent(
    "Can we schedule a call for next Tuesday at 2pm?"
)
print(result["primary_intent"])  # "scheduling_request"

# Parse thread
thread = server.parse_thread(raw_email_content, format="raw")

# Extract context
context = server.extract_context(thread_id=thread["thread_id"])
print(context["context"]["detected_intent"])
print(context["context"]["mentioned_dates"])

# Generate reply headers
headers = server.maintain_thread(
    original_message_id="<abc123@example.com>",
    original_references=[],
    original_subject="Meeting Request",
    is_reply=True
)
```

## Integration

This MCP server integrates with:

- **COMMUNICATOR agent**: Uses intent detection for response drafting
- **SCHEDULER agent**: Extracts dates/times for calendar operations
- **ghl-mcp**: Syncs parsed context to CRM contact notes
- **Unified Integration Gateway**: Centralized API management

## Storage

Parsed threads are saved to `.hive-mind/threads/` for:
- Self-annealing learning
- Pattern analysis
- Compliance audit

## License

MIT
