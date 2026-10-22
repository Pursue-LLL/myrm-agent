# Model Tester Subsystem Architecture

## Overview
Provides instant connectivity, TTFT (time-to-first-token) latency, and throughput testing for LLM model configurations and switching views.

## Components & Files
| File | Role | Primary Consumers |
|---|---|---|
| `modelTesterTypes.ts` | Pure domain types for model ping requests and health results | UI & service layers |
| `modelTesterService.ts` | Client API layer communicating with `/system/model-ping` | `ModelPingSpeedTester.tsx` |
| `ModelPingSpeedTester.tsx` | Instant ping button & TTFT latency badge component | Settings & Model selectors |
| `index.ts` | Module export facade | External consumers |
