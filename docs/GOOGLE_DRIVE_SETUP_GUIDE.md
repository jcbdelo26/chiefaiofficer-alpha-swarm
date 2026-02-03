# 🔐 Google Drive OAuth Setup Guide

**Purpose**: Enable your swarm to access Google Drive documents programmatically

**Use Cases**:
- Read customer onboarding documents
- Access sales collateral for campaign personalization
- Analyze meeting notes and transcripts
- Pull company research from shared folders

---

## 📋 Prerequisites

- Google Workspace account (josh@chiefaiofficer.com)
- Access to Google Cloud Console
- 15 minutes of setup time

---

## 🚀 Step-by-Step Setup

### **Step 1: Create Google Cloud Project**

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Sign in with **josh@chiefaiofficer.com**
3. Click **"Select a Project"** → **"New Project"**
4. **Project name**: `ChiefAIOfficer-AlphaSwarm`
5. Click **"Create"**

---

### **Step 2: Enable Google Drive API**

1. In the Cloud Console, go to **"APIs & Services"** → **"Library"**
2. Search for **"Google Drive API"**
3. Click on it → Click **"Enable"**
4. Also enable **"Google Sheets API"** (useful for data export)
5. Also enable **"Google Docs API"** (for document parsing)

---

### **Step 3: Create OAuth 2.0 Credentials**

1. Go to **"APIs & Services"** → **"Credentials"**
2. Click **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
3. If prompted, **Configure Consent Screen** first:
   - User Type: **Internal** (if using Workspace) or **External**
   - App name: `Chief AI Officer Alpha Swarm`
   - User support email: **josh@chiefaiofficer.com**
   - Developer contact: **josh@chiefaiofficer.com**
   - Scopes: Add these:
     - `https://www.googleapis.com/auth/drive.readonly` (read Drive files)
     - `https://www.googleapis.com/auth/documents.readonly` (read Docs)
     - `https://www.googleapis.com/auth/spreadsheets.readonly` (read Sheets)
   - Test users: Add **josh@chiefaiofficer.com**
   - Click **"Save and Continue"**

4. Back to **"Create OAuth client ID"**:
   - Application type: **Desktop app**
   - Name: `AlphaSwarm-Desktop`
   - Click **"Create"**

5. **Download JSON**:
   - Click **"Download JSON"** button
   - Save as `credentials.json`
   - Move to project root: `d:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm\credentials.json`

---

### **Step 4: Install Python Libraries**

Add to `requirements.txt`:
```txt
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
google-api-python-client==2.115.0
```

Install:
```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

---

### **Step 5: Authenticate (First Time Only)**

Run this script to generate `token.json` (your access token):

```bash
# Create authentication script
python execution/google_drive_auth.py
```

This will:
1. Open your browser
2. Ask you to sign in with **josh@chiefaiofficer.com**
3. Request permissions for Drive access
4. Save `token.json` to project root

**Important**: 
- `credentials.json` and `token.json` are in `.gitignore` (never commit!)
- `token.json` expires periodically, script will auto-refresh

---

### **Step 6: Test Access**

```bash
# Test Google Drive access
python -c "
from execution.google_drive_helper import GoogleDriveHelper
gdrive = GoogleDriveHelper()
files = gdrive.list_files(folder_id='1LKzqvLMWQgAfMIp5YQClZYKp0nzvooiv')
print(f'Found {len(files)} files in folder')
for f in files[:5]:
    print(f'  - {f[\"name\"]} ({f[\"mimeType\"]})')
"
```

---

## 📁 Files Created

After setup, you'll have:

```
chiefaiofficer-alpha-swarm/
├── credentials.json          # OAuth credentials (DO NOT COMMIT)
├── token.json                # Access token (DO NOT COMMIT)
├── .gitignore                # Already includes these ✓
├── execution/
│   ├── google_drive_auth.py # Authentication script
│   └── google_drive_helper.py # Helper class for Drive access
```

---

## 🔧 Usage in Your Swarm

### **List Files in Folder**
```python
from execution.google_drive_helper import GoogleDriveHelper

gdrive = GoogleDriveHelper()
files = gdrive.list_files(folder_id='1LKzqvLMWQgAfMIp5YQClZYKp0nzvooiv')
```

### **Download Document**
```python
# Download Google Doc as text
content = gdrive.download_doc(file_id='abc123')

# Download PDF
gdrive.download_file(file_id='abc123', output_path='./downloads/doc.pdf')
```

### **Read Google Sheet**
```python
# Read spreadsheet as pandas DataFrame
df = gdrive.read_sheet(file_id='abc123', sheet_name='Sheet1')
```

---

## 🔐 Security Best Practices

1. **Never commit credentials**:
   ```bash
   # Verify they're in .gitignore
   cat .gitignore | grep credentials.json
   cat .gitignore | grep token.json
   ```

2. **Use service account for production** (optional, advanced):
   - Create a service account instead of OAuth
   - Share Drive folder with service account email
   - No browser authentication needed

3. **Limit scopes**:
   - Use `.readonly` scopes unless you need write access
   - Don't request more permissions than needed

---

## 🆘 Troubleshooting

### **Error: "The project does not have access to Drive API"**
- Go to APIs & Services → Library
- Enable Google Drive API

### **Error: "Access blocked: This app's request is invalid"**
- Configure OAuth consent screen
- Add your email as a test user

### **Error: "invalid_grant"**
- Delete `token.json`
- Re-run `python execution/google_drive_auth.py`

### **Token expires constantly**
- Normal behavior (tokens expire after ~1 hour)
- Refresh token lasts ~6 months
- Script auto-refreshes using refresh token

---

## 💡 Advanced: Service Account (Optional)

For production deployments without browser authentication:

1. Create service account in Google Cloud Console
2. Download JSON key
3. Share Drive folder with service account email
4. Use service account credentials instead of OAuth

**When to use**:
- Docker/server deployments
- Automated workflows
- No human authentication available

---

## ✅ Checklist

- [ ] Created Google Cloud project
- [ ] Enabled Drive, Docs, Sheets APIs
- [ ] Created OAuth credentials
- [ ] Downloaded `credentials.json`
- [ ] Installed Python libraries
- [ ] Ran authentication script
- [ ] Generated `token.json`
- [ ] Verified files are in `.gitignore`
- [ ] Tested Drive access

Once complete, your swarm can access Google Drive documents programmatically! 🚀
