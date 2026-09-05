---
name: architecture-diagram
description: >-
  Generate interactive system architecture diagrams, workflows, sequence flows, and data pipelines as standard .arch.json artifacts. Rendered natively with auto-layout, interactive path tracing, and evolution diffing.
version: 2.0.0
category: creative
tags:
  - architecture
  - diagrams
  - interactive
  - visualization
  - infrastructure
  - system-design
allowed-tools: file_write_tool file_read_tool
contract:
  steps:
    - "Phase 1: Understand & Analyze — gather system components, connections, protocols, and layers"
    - "Phase 2: Topology Structuring — classify into 5 diagram types (architecture, workflow, sequence, dataflow, lifecycle)"
    - "Phase 3: JSON IR Generation — construct valid .arch.json with nodes, edges, groups, and semantic roles"
    - "Phase 4: Deliver — save with file_write_tool as *.arch.json for instant native interactive rendering"
  potential_traps:
    - description: "Attempting to calculate manual SVG pixel coordinates (x, y)"
      mitigation: "Strictly output pure JSON IR topology; layout geometry is automatically calculated by the rendering engine"
      severity: critical
    - description: "Dangling edges referencing nonexistent node IDs"
      mitigation: "Ensure every edge source and target exactly matches a declared node id"
      severity: high
  verification_steps:
    - step_id: valid_arch_json
      description: "Output file is saved as *.arch.json with valid nodes and edges"
      validation_method: "Verify JSON syntax and ensure all edge source/target IDs exist in nodes"
      is_required: true
  success_criteria: "High-fidelity interactive architecture artifact rendered seamlessly with path tracing and evolution diff capability"
  estimated_duration_seconds: 180
---

# Interactive Architecture & System Topology

Generate interactive system architecture maps, workflows, sequence diagrams, and data pipelines as structured `.arch.json` artifacts.
The artifact is rendered in real-time by the native interactive canvas with automatic layout (zero coordinate calculation needed), node search, upstream/downstream path tracing, and multi-version evolution diffing.

## Diagram Types Supported

1. **`architecture`** — System components, microservices, databases, caches, gateways, cloud infra.
2. **`workflow`** — Business processes, state transitions, step-by-step orchestrations.
3. **`sequence`** — Message dispatch, request/response lifecycles, cross-service call flows.
4. **`dataflow`** — ETL pipelines, event streams, queue processing, read/write replication.
5. **`lifecycle`** — Entity lifecycle states, deployment phases, rollouts.

## JSON IR Schema Specification

Always save the output as a `.arch.json` file (e.g. `system-architecture.arch.json`) using `file_write_tool`.

```json
{
  "version": "1.0.0",
  "diagram_type": "architecture",
  "title": "System Architecture Overview",
  "description": "High-level service topology, gateway routing, and persistence layer",
  "groups": [
    {
      "id": "client-tier",
      "label": "Client Tier",
      "color": "cyan"
    },
    {
      "id": "service-mesh",
      "label": "Core Microservices",
      "color": "emerald"
    },
    {
      "id": "storage-tier",
      "label": "Storage & Persistence",
      "color": "violet"
    }
  ],
  "nodes": [
    {
      "id": "web-app",
      "label": "Web Client (Next.js)",
      "type": "frontend",
      "group_id": "client-tier",
      "tech_stack": "Next.js / React 19",
      "description": "Responsive SPA delivering desktop and mobile UX",
      "status": "normal"
    },
    {
      "id": "api-gateway",
      "label": "API Gateway",
      "type": "gateway",
      "group_id": "service-mesh",
      "tech_stack": "FastAPI / Nginx",
      "description": "Reverse proxy, rate limiting, and JWT validation",
      "status": "normal"
    },
    {
      "id": "order-service",
      "label": "Order Service",
      "type": "backend",
      "group_id": "service-mesh",
      "tech_stack": "Python / AsyncIO",
      "description": "Handles cart checkout and transactional state",
      "status": "normal"
    },
    {
      "id": "postgres-db",
      "label": "Primary PostgreSQL",
      "type": "database",
      "group_id": "storage-tier",
      "tech_stack": "PostgreSQL 16",
      "description": "ACID relational store with WAL replication",
      "status": "normal"
    },
    {
      "id": "redis-cache",
      "label": "Redis Cache Cluster",
      "type": "cache",
      "group_id": "storage-tier",
      "tech_stack": "Redis 7.2",
      "description": "Session cache and hot catalog cache",
      "status": "normal"
    }
  ],
  "edges": [
    {
      "source": "web-app",
      "target": "api-gateway",
      "label": "HTTPS / WSS",
      "protocol": "HTTPS",
      "animated": true,
      "style": "solid"
    },
    {
      "source": "api-gateway",
      "target": "order-service",
      "label": "Internal RPC",
      "protocol": "gRPC",
      "animated": false,
      "style": "solid"
    },
    {
      "source": "order-service",
      "target": "redis-cache",
      "label": "Cache Lookups",
      "protocol": "RESP",
      "animated": false,
      "style": "solid"
    },
    {
      "source": "order-service",
      "target": "postgres-db",
      "label": "Read/Write SQL",
      "protocol": "SQL",
      "animated": false,
      "style": "solid"
    }
  ]
}
```

## Node Category & Palette Guidelines

Use these standard categories for auto-theming:
- `frontend` — Client interfaces, browsers, apps (Cyan)
- `gateway` — API Gateways, load balancers, proxies (Amber)
- `backend` — Microservices, serverless functions, RPC services (Emerald)
- `database` — Relational DBs, NoSQL, graph databases (Violet)
- `cache` — In-memory stores, Redis, Memcached (Orange)
- `queue` — Kafka, RabbitMQ, SQS, event streams (Rose)
- `external` — Third-party APIs, SaaS, Stripe, GitHub (Slate)

## Rules for Agents

1. **Never output absolute SVG pixel coordinates**: The rendering engine handles 100% of the geometric placement using DAG layout algorithms.
2. **Every edge must be valid**: `source` and `target` must point to existing node IDs.
3. **Keep diagrams readable**: Aim for 8 to 25 components per diagram. Group tightly-coupled components under logical `groups`.
4. **Always use `.arch.json` extension**: Ensures the artifact is immediately mounted into the interactive canvas.
