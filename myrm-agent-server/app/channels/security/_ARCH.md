# security/

## Overview
Webhook security layer. Defines inbound security protocols (signature verification,

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Webhook security layer. Defines inbound security protocols (signature verification, | ✅ |
| context.py | Core | Request context layer. Encapsulates validated request data and verification result objects. | ✅ |
| errors.py | Core | Webhook error response layer. Provides RFC 7807 standardized error format, | ✅ |
| ip_utils.py | Core | IP extraction utility layer. Provides trusted proxy validation and real IP extraction, | ✅ |
| protocols.py | Core | Security protocol layer. Defines standard webhook security verification interfaces, | ✅ |
| webhook_middleware.py | Core | Webhook security middleware layer. Unified inbound security verification (body limits, | ✅ |
