# Google Calendar MCP Server

Model Context Protocol server for Google Calendar operations with built-in guardrails.

## Features

- **get_availability**: Check calendar availability for a time range
- **create_event**: Create calendar events with Zoom link support
- **update_event**: Modify existing events
- **delete_event**: Cancel events with attendee notifications
- **get_events**: List events in a date range
- **find_available_slots**: Find meeting slots across multiple calendars

## Guardrails

The server enforces these rules to prevent scheduling issues:

| Rule | Value | Description |
|------|-------|-------------|
| Working Hours | 9 AM - 6 PM | Configurable per timezone |
| Buffer | 15 minutes | Minimum between meetings |
| Rate Limit | 100/hour | API request limit |
| Max Duration | 2 hours | Maximum meeting length |
| Max Attendees | 50 | Per meeting |
| Weekend | Blocked | Unless explicitly allowed |

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Google Cloud Console Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project or select existing
3. Enable the **Google Calendar API**
4. Create OAuth 2.0 credentials (Desktop app)
5. Download `credentials.json` to the project root

### 3. First Run Authentication

```bash
python server.py
```

This will open a browser for OAuth consent. After authorization, `token.json` will be created.

## Usage

### With Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "google-calendar-mcp": {
      "command": "python",
      "args": ["mcp-servers/google-calendar-mcp/server.py"]
    }
  }
}
```

### Programmatic Usage

```python
from mcp_servers.google_calendar_mcp import GoogleCalendarMCP

server = GoogleCalendarMCP()

# Check availability
avail = await server.get_availability(
    calendar_id="primary",
    start_time="2026-01-22T09:00:00-05:00",
    end_time="2026-01-22T17:00:00-05:00"
)

# Create event with guardrails
result = await server.create_event(
    title="Strategy Meeting",
    start_time="2026-01-22T14:00:00-05:00",
    end_time="2026-01-22T14:30:00-05:00",
    attendees=["team@example.com"],
    zoom_link="https://zoom.us/j/123456789"
)

# Find available slots across calendars
slots = await server.find_available_slots(
    calendar_ids=["primary", "team@example.com"],
    duration_minutes=30,
    working_hours_start=9,
    working_hours_end=17
)
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CALENDAR_MAX_REQUESTS_PER_HOUR` | 100 | Rate limit |
| `CALENDAR_DEFAULT_TIMEZONE` | America/New_York | Default TZ |
| `CALENDAR_WORKING_HOURS_START` | 9 | Working day start |
| `CALENDAR_WORKING_HOURS_END` | 18 | Working day end |

## Error Handling

The server returns structured responses:

```json
{
  "success": false,
  "error": "Meeting starts before working hours (9:00)",
  "suggestions": ["Schedule after 9:00 America/New_York"]
}
```

## Integration with Unified Swarm

This MCP server integrates with:
- **SCHEDULER agent**: Primary consumer for meeting scheduling
- **COMMUNICATOR agent**: Uses availability for email responses
- **Unified Integration Gateway**: Centralized API management

## License

MIT
