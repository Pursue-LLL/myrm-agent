---
name: google-workspace
description: >-
  Interact with Google Workspace services (Gmail, Calendar, Drive, Docs) via
  Google APIs. Manage emails, schedule events, create documents, and organize
  files programmatically.
version: 1.0.0
category: productivity
tags:
  - google
  - gmail
  - calendar
  - drive
  - docs
  - productivity
allowed-tools: web_fetch_tool bash_tool file_write_tool
requires:
  env: [GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET]
contract:
  steps:
    - "Phase 1: Authenticate — verify Google API credentials and scopes"
    - "Phase 2: Discover — identify target service and resource"
    - "Phase 3: Execute — perform the requested operations"
    - "Phase 4: Verify — confirm results and handle errors"
  potential_traps:
    - description: "OAuth token expired or insufficient scopes"
      mitigation: "Check token validity before operations; guide user through re-auth if needed"
      severity: high
    - description: "Deleting or overwriting important data"
      mitigation: "Always confirm destructive operations; prefer creating new versions over overwriting"
      severity: critical
  success_criteria: "Requested Google Workspace operations completed and verified"
  estimated_duration_seconds: 300
---

# Google Workspace

## Overview

Google Workspace (Gmail, Calendar, Drive, Docs, Sheets) is the most widely used productivity suite. This skill provides structured workflows for interacting with Google services via their REST APIs.

## Prerequisites

The user needs Google API credentials:

1. Go to https://console.cloud.google.com/
2. Create or select a project
3. Enable required APIs (Gmail, Calendar, Drive, etc.)
4. Create OAuth 2.0 credentials or API key
5. Set credentials in environment

## Gmail Operations

### List Recent Emails

```
GET https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=10&q=QUERY
```

Query syntax: `from:sender@example.com`, `subject:meeting`, `is:unread`, `after:2024/01/01`

### Read Email

```
GET https://gmail.googleapis.com/gmail/v1/users/me/messages/MESSAGE_ID?format=full
```

### Send Email

```
POST https://gmail.googleapis.com/gmail/v1/users/me/messages/send
Body: {"raw": "BASE64_ENCODED_RFC2822_MESSAGE"}
```

### Search Patterns

| Goal | Query |
|------|-------|
| Unread from person | `from:name@example.com is:unread` |
| Recent with attachment | `has:attachment newer_than:7d` |
| Specific subject | `subject:"weekly report"` |
| In a label | `label:important` |

## Calendar Operations

### List Upcoming Events

```
GET https://www.googleapis.com/calendar/v3/calendars/primary/events?timeMin=NOW&maxResults=10&singleEvents=true&orderBy=startTime
```

### Create Event

```
POST https://www.googleapis.com/calendar/v3/calendars/primary/events
{
  "summary": "Meeting Title",
  "start": {"dateTime": "2024-01-15T10:00:00-07:00"},
  "end": {"dateTime": "2024-01-15T11:00:00-07:00"},
  "attendees": [{"email": "attendee@example.com"}],
  "description": "Meeting agenda..."
}
```

### Update Event

```
PATCH https://www.googleapis.com/calendar/v3/calendars/primary/events/EVENT_ID
```

## Drive Operations

### List Files

```
GET https://www.googleapis.com/drive/v3/files?q=QUERY&pageSize=20
```

Query: `name contains 'report'`, `mimeType='application/pdf'`, `'FOLDER_ID' in parents`

### Upload File

```
POST https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart
```

### Create Folder

```
POST https://www.googleapis.com/drive/v3/files
{"name": "New Folder", "mimeType": "application/vnd.google-apps.folder"}
```

## Workflow Patterns

### Morning Briefing
1. Check unread emails (last 12 hours, high priority)
2. List today's calendar events
3. Compile into a structured summary

### Meeting Preparation
1. Find the calendar event details
2. Search emails related to the topic
3. Locate relevant Drive documents
4. Create a preparation brief

### Email Triage
1. List unread emails grouped by sender/topic
2. Categorize: urgent / needs-reply / FYI / archive
3. Draft replies for urgent items (user confirms before sending)

### Weekly Report
1. Gather completed calendar events (past week)
2. Search for relevant email threads
3. Create a structured summary document
4. Upload to Drive in the appropriate folder

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Token expired | Refresh OAuth token |
| 403 Forbidden | Insufficient scopes | Re-authorize with required scopes |
| 404 Not Found | Wrong resource ID | Verify the ID via list endpoints |
| 429 Rate Limit | Too many requests | Back off and retry with exponential delay |
