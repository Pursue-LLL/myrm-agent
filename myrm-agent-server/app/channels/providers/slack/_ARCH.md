# slack/

## Overview
Slack channel provider package with AI Agent status indicator support.
Outbound messages automatically set assistant thread status ("is thinking...")
when a streaming placeholder is sent, and clear it upon reply completion.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Slack channel provider package. | — |
| api.py | Core | Slack Web API client. Wraps HTTP calls, streaming, assistant thread status, and error handling. | ✅ |
| channel.py | Core | Slack Bot channel with AI Agent status indicator. Supports DM/channel/thread messages, file upload, streaming, and assistant.threads.setStatus. | ✅ |
| format_converter.py | Core | Markdown → Slack mrkdwn converter. Escapes special chars (&, <, >), | ✅ |
| helpers.py | Core | Slack pure-function helpers — Block Kit builder and inbound event parsing. | ✅ |
| thread_tracker.py | Core | Slack thread tracker for auto-reply functionality. | ✅ |
| user_resolver.py | Core | Slack user resolver. Calls users.info API to fetch display_name/real_name. | ✅ |

## Key Dependencies

- `infra`
