# Design: HTTP Gateway

> External HTTP interface for Presidium-governed agent systems.

**Status:** Draft (deferred to M4/M5)
**Package:** TBD (possibly part of `presidium-sdk`)
**Milestone:** M4+

## Problem Statement

Production agent systems need HTTP interfaces for: triggering agent tasks, querying agent status, viewing governance dashboards, and integrating with existing enterprise systems. Civitas has an HTTP Gateway — Presidium needs to extend it with governance endpoints.

## Goals

1. REST API for governance operations (registry, policy, eval queries)
2. Extend Civitas's HTTP Gateway with governance routes
3. OpenAPI documentation for all endpoints
4. Authentication and authorization on governance endpoints

## Non-Goals

- Building a full web dashboard (that's a frontend project)
- Replacing Civitas's HTTP Gateway (extending it)
- Real-time WebSocket streams (future scope)

## Design (Sketch)

### Governance API Endpoints

```
GET    /api/v1/agents                    # List registered agents
GET    /api/v1/agents/{name}             # Get agent details
GET    /api/v1/agents/{name}/trust       # Trust score history
POST   /api/v1/agents/{name}/suspend     # Suspend an agent

GET    /api/v1/policies                  # List policies
GET    /api/v1/policies/{name}           # Get policy details
POST   /api/v1/policies/validate         # Validate policy YAML

GET    /api/v1/eval/{agent}              # Get latest eval metrics
GET    /api/v1/eval/{agent}/history      # Eval metric history

GET    /api/v1/approvals                 # Pending approval queue
POST   /api/v1/approvals/{id}/approve    # Approve an action
POST   /api/v1/approvals/{id}/deny       # Deny an action

GET    /api/v1/costs                     # LLM cost summary
GET    /api/v1/costs/{agent}             # Per-agent cost breakdown
```

## Open Questions

- This is a thin layer over the other packages. Does it warrant its own package?
- Should this extend Civitas's HTTPGateway or be standalone?
- Authentication: API keys? OAuth? JWT?
- This is deferred — how much design is needed now vs. at implementation time?
