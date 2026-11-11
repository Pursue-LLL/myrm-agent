# probe/

## Overview
Network probes and charset detection for web fetch decoding.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports HTTP/3 probe helpers | ✅ |
| http3_probe.py | Util | HTTP/3 protocol probe and retry metrics | ✅ |
| charset_detector.py | Util | Tiered charset detection: header charset, `<meta>` charset, strict UTF-8, CJK trial decodes, then a replacement decode. `partial` marks a body cut at an arbitrary byte: its last half character is dropped, so the cut cannot fail the strict decodes or let a CJK trial decode read the page as mojibake | ✅ |

## Dependencies

- `scrapling` (HTTP/3 probe, imported when a probe runs); the charset detector needs only the standard library
