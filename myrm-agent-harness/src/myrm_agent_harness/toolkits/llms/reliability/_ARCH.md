# reliability/

## Overview
Retry timing for model calls: jittered delays that keep concurrent sessions from retrying in lockstep, and the long adaptive schedule for PAAS overload errors.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| jittered_backoff.py | Core | `calculate_jittered_delay`, `is_paas_overload_error`, `calculate_adaptive_jittered_delay`, `paas_overload_retry_ceiling`: jittered exponential delays and the adaptive ladder for PAAS overloads. | ✅ |
