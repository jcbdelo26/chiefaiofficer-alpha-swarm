# RB2B Quick Start Script
# Run this to set up RB2B webhook integration automatically

Write-Host "================================" -ForegroundColor Cyan
Write-Host "RB2B Webhook Setup Assistant" -ForegroundColor Cyan
Write-Host "================================`n" -ForegroundColor Cyan

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "❌ Error: .env file not found" -ForegroundColor Red
    Write-Host "Please run this from the chiefaiofficer-alpha-swarm directory" -ForegroundColor Yellow
    exit 1
}

# Step 1: Check Supabase credentials
Write-Host "Step 1: Checking Supabase credentials..." -ForegroundColor Yellow
$env_content = Get-Content ".env" -Raw
if ($env_content -match "SUPABASE_URL=(.+)" -and $Matches[1] -ne "") {
    Write-Host "✓ Supabase URL found" -ForegroundColor Green
}
else {
    Write-Host "❌ Supabase URL not configured" -ForegroundColor Red
    exit 1
}

# Step 2: Create Supabase table
Write-Host "`nStep 2: Creating Supabase table..." -ForegroundColor Yellow
Write-Host "Please run this SQL in Supabase SQL Editor:" -ForegroundColor Cyan
Write-Host @"

CREATE TABLE IF NOT EXISTS rb2b_visitors (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    rb2b_visitor_id TEXT UNIQUE,
    company_name TEXT,
    company_domain TEXT,
    company_industry TEXT,
    company_size TEXT,
    company_revenue TEXT,
    company_location TEXT,
    visitor_ip TEXT,
    visitor_country TEXT,
    visitor_city TEXT,
    page_url TEXT,
    referrer TEXT,
    user_agent TEXT,
    session_id TEXT,
    identified_at TIMESTAMPTZ,
    raw_data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rb2b_company_domain ON rb2b_visitors(company_domain);
CREATE INDEX IF NOT EXISTS idx_rb2b_identified_at ON rb2b_visitors(identified_at DESC);

"@ -ForegroundColor White

$response = Read-Host "`nHave you created the table? (y/n)"
if ($response -ne "y") {
    Write-Host "Please create the table first, then run this script again" -ForegroundColor Yellow
    exit 0
}

# Step 3: Start ngrok (for local testing)
Write-Host "`nStep 3: Setting up webhook URL..." -ForegroundColor Yellow
$use_ngrok = Read-Host "Are you testing locally? (y/n)"

if ($use_ngrok -eq "y") {
    Write-Host "`nStarting ngrok..." -ForegroundColor Cyan
    
    # Check if ngrok is installed
    $ngrok_path = Get-Command ngrok -ErrorAction SilentlyContinue
    if (-not $ngrok_path) {
        Write-Host "❌ ngrok not found. Please install from https://ngrok.com/download" -ForegroundColor Red
        exit 1
    }
    
    # Start ngrok in background
    Start-Process -FilePath "ngrok" -ArgumentList "http 8000" -WindowStyle Normal
    Start-Sleep -Seconds 3
    
    # Get ngrok URL
    try {
        $ngrok_api = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels"
        $webhook_url = $ngrok_api.tunnels[0].public_url + "/webhooks/rb2b"
        Write-Host "✓ Ngrok URL: $webhook_url" -ForegroundColor Green
    }
    catch {
        Write-Host "❌ Could not get ngrok URL. Please check ngrok is running" -ForegroundColor Red
        exit 1
    }
}
else {
    $webhook_url = Read-Host "Enter your production webhook URL (e.g., https://your-domain.com/webhooks/rb2b)"
}

# Step 4: Get webhook secret
Write-Host "`nStep 4: Configure RB2B webhook secret..." -ForegroundColor Yellow
Write-Host @"

Go to RB2B Dashboard:
1. Navigate to Integrations → Webhook
2. Enable the integration (toggle Status to ON)
3. Paste this URL in 'Webhook URL' field:
   $webhook_url
4. Click Save
5. Copy the Webhook Secret shown

"@ -ForegroundColor Cyan

$webhook_secret = Read-Host "Paste your RB2B Webhook Secret here"

if ($webhook_secret) {
    # Update .env file
    $env_content = $env_content -replace "RB2B_WEBHOOK_SECRET=.*", "RB2B_WEBHOOK_SECRET=$webhook_secret"
    Set-Content ".env" $env_content
    Write-Host "✓ Webhook secret saved to .env" -ForegroundColor Green
}

# Step 5: Start webhook server
Write-Host "`nStep 5: Starting webhook server..." -ForegroundColor Yellow
Write-Host "Starting Python webhook server..." -ForegroundColor Cyan

Start-Process -FilePath "python" -ArgumentList "webhooks/rb2b_webhook.py" -WindowStyle Normal

Start-Sleep -Seconds 2

# Step 6: Test connection
Write-Host "`nStep 6: Testing connection..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "http://localhost:8000/webhooks/rb2b/health"
    if ($health.status -eq "healthy") {
        Write-Host "✓ Webhook server is healthy!" -ForegroundColor Green
        Write-Host "  - Supabase: $($health.supabase_configured)" -ForegroundColor White
        Write-Host "  - Secret: $($health.secret_configured)" -ForegroundColor White
    }
}
catch {
    Write-Host "⚠ Could not connect to webhook server" -ForegroundColor Yellow
    Write-Host "Please check if Python server started successfully" -ForegroundColor Yellow
}

# Final instructions
Write-Host "`n================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "================================`n" -ForegroundColor Cyan

Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Go to RB2B and click 'Send test event'" -ForegroundColor White
Write-Host "2. Check Supabase → rb2b_visitors table for test data" -ForegroundColor White
Write-Host "3. Monitor webhook server terminal for incoming events`n" -ForegroundColor White

Write-Host "Webhook URL: $webhook_url" -ForegroundColor Cyan
Write-Host "Health Check: http://localhost:8000/webhooks/rb2b/health`n" -ForegroundColor Cyan

Write-Host "Press any key to exit..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
