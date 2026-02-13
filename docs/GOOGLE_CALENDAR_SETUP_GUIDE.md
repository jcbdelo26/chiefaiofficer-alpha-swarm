# Google Calendar Setup Guide — Meeting Booking Agent

**For:** Head of Sales (non-technical)
**Time needed:** ~10 minutes
**What this does:** Connects the CAIO swarm's scheduling agent to your Google Calendar so it can check your availability, book discovery calls, and send calendar invites automatically.

---

## What You'll Need

- Access to the Google account whose calendar you want to use for meetings
- A web browser
- Access to this project folder on the computer

---

## Step 1: Enable the Google Calendar API

Your Google Cloud project already exists (`psyched-span-484417-q6`), but the Calendar API may not be turned on yet.

1. Open this link in your browser:
   **https://console.cloud.google.com/apis/library/calendar-json.googleapis.com?project=psyched-span-484417-q6**

2. Click the blue **"Enable"** button
   - If it says "API enabled" instead, you're already set — skip to Step 2

3. Wait a few seconds for it to activate

> **Why?** The swarm already has Gmail access. This step adds Calendar access to the same Google project.

---

## Step 2: Run the Authorization Flow

This step opens a browser window where you sign in with your Google account and give the swarm permission to manage your calendar.

1. Open a **Command Prompt** or **Terminal**

2. Navigate to the project folder:
   ```
   cd "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
   ```

3. Run this command:
   ```
   python scripts/setup_google_calendar.py
   ```

4. A browser window will open automatically:
   - **Sign in** with the Google account you want to use
   - You'll see a screen saying *"This app wants to access your Google Account"*
   - Click **"Continue"** (you may need to click "Advanced" > "Go to... (unsafe)" first — this is normal for internal apps)
   - Check the box for **"See, edit, share, and permanently delete all the calendars you can access using Google Calendar"**
   - Click **"Continue"**

5. The browser will show "The authentication flow has completed." You can close it.

6. Back in the terminal, you should see:
   ```
   Calendar authorization successful!
   Token saved to token.json
   ```

> **What happened?** The swarm now has a token (like a key) that lets it read your calendar and create events. This token refreshes automatically — you only need to do this once.

---

## Step 3: Verify It Works

Run this command to test:
```
python scripts/setup_google_calendar.py --test
```

You should see something like:
```
Connected to calendar: your.email@gmail.com
Upcoming events (next 7 days):
  - Team standup (Mon 9:00 AM)
  - Client call (Tue 2:00 PM)
  ...
Calendar integration is working!
```

---

## Step 4: Configure Your Preferences (Optional)

The scheduler has sensible defaults, but you can customize:

| Setting | Default | How to Change |
|---------|---------|---------------|
| Working hours start | 9:00 AM | Set `CALENDAR_WORKING_HOURS_START=8` in Railway |
| Working hours end | 6:00 PM | Set `CALENDAR_WORKING_HOURS_END=17` in Railway |
| Default timezone | America/New_York (EST) | Set `CALENDAR_DEFAULT_TIMEZONE=America/Los_Angeles` |
| Buffer between meetings | 15 minutes | Built-in, not configurable |
| Meeting duration | 30 minutes | Set per-meeting by the agent |
| Max days ahead for booking | 14 days | Built-in, not configurable |

To change these in Railway:
1. Go to **https://railway.app** > your project > `caio-swarm-dashboard` service
2. Click **Variables** tab
3. Click **New Variable**
4. Add the variable name and value from the table above
5. Click **Deploy** to apply

---

## Step 5: Deploy to Railway

After completing Steps 1-3 locally, the `token.json` file needs to be available on Railway:

1. The `token.json` contains your calendar access token
2. Open the file and copy its contents
3. In Railway, add a new variable:
   - **Name:** `GOOGLE_CALENDAR_TOKEN_JSON`
   - **Value:** (paste the contents of token.json)
4. The app will read this on startup

> **Security note:** `credentials.json` and `token.json` are in `.gitignore` and will never be pushed to GitHub. The Railway environment variable is the safe way to pass them to production.

---

## How the Scheduler Works (For Reference)

Once configured, the scheduling agent will:

1. **Check your calendar** for free slots when a prospect is ready to book
2. **Propose 3-5 time options** in the prospect's timezone
3. **Handle back-and-forth** if the prospect counters (up to 5 exchanges)
4. **Book the meeting** on your Google Calendar with:
   - Meeting title (e.g., "Discovery Call - John Smith, Acme Corp")
   - Zoom link (auto-generated)
   - Calendar invite sent to both you and the prospect
5. **Set reminders** at 24 hours and 1 hour before the meeting
6. **Update GHL** with the meeting details on the contact record
7. **Trigger the Researcher agent** to prepare a meeting briefing

### Safety guardrails built in:
- Won't book outside your working hours (9 AM - 6 PM)
- Won't double-book (checks existing events)
- 15-minute buffer between meetings
- 2-hour minimum notice for new bookings
- Escalates to you after 5 failed scheduling attempts
- All bookings are logged in `.hive-mind/scheduler/`

---

## Troubleshooting

### "The app isn't verified" warning
This is normal for internal Google Cloud apps. Click **Advanced** > **Go to [app name] (unsafe)** to proceed. Your app is private and only used by your team.

### "Token expired" error
Run Step 2 again. The token auto-refreshes, but if it's been revoked or the refresh token expired, you'll need to re-authorize.

### "Calendar API not enabled" error
Go back to Step 1 and make sure the Calendar API is enabled in your Google Cloud project.

### "Permission denied" error
Make sure you authorized the correct Google account (the one whose calendar you want to manage). Run Step 2 again with the right account.

### Need to change which Google account is used?
Delete `token.json` from the project folder, then run Step 2 again. It will prompt you to sign in fresh.

---

## Quick Reference

| Item | Location |
|------|----------|
| Google Cloud Console | https://console.cloud.google.com/apis/credentials?project=psyched-span-484417-q6 |
| OAuth Credentials | `credentials.json` (already configured, don't modify) |
| Access Token | `token.json` (auto-generated, auto-refreshes) |
| Scheduler Agent | `execution/scheduler_agent.py` |
| Calendar MCP Server | `mcp-servers/google-calendar-mcp/server.py` |
| Scheduling Logs | `.hive-mind/scheduler/` |
| Railway Dashboard | https://railway.app (caio-swarm-dashboard service) |
