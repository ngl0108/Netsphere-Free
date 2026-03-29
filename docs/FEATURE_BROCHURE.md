# NetSphere Feature Brochure

## Product summary

NetSphere is a multi-vendor network operations platform built for discovery, topology understanding, controlled change, and operational proof.

It is positioned as:

- NMS plus network automation
- topology plus path intelligence
- automation plus approval and rollback control

## Core value

NetSphere reduces the gap between seeing the network and acting on it safely.

## What it does

### 1. Discovery and inventory

- seed and crawl based discovery
- vendor-aware identification
- inventory normalization across multiple device families

### 2. Multi-layer topology

- L2 adjacency visibility
- L3 topology visibility
- BGP topology visibility
- VXLAN and overlay visibility
- hybrid cloud and on-prem visibility
- real-time SSE event stream for topology changes
- topology snapshot comparison and diff

#### Interactive layout editor

NetSphere includes a full NMS-grade topology editor:

- drag-and-drop node positioning with snap-to-grid
- manual link creation with color, thickness, curve type, and line style options
- group box zones with custom colors, auto-fit, and child arrangement
- auto-discovered link override (label, color, style) without changing topology data
- undo / redo (Ctrl+Z / Ctrl+Y) with 40-step history
- keyboard shortcuts: Ctrl+S save, Delete remove, Ctrl+A select all, Escape deselect
- right-click context menu with contextual actions per node, link, or canvas
- Shift+Click multi-select for batch operations
- per-user layout persistence with JSON import/export

### 3. Path and fault understanding

- path trace with segment metadata
- degraded-link handling
- structured diagnosis with likely cause and next actions

### 4. Controlled automation

- compliance-aware remediation planning
- approval-integrated execution
- rollback and post-check guardrails
- issue-driven closed-loop automation

### 5. Operational proof

- KPI readiness reporting
- vendor support matrix
- synthetic and EVE validation evidence
- release evidence summary for go/no-go discussions

## Differentiators

- the same UI can pivot between L2, L3, BGP, VXLAN, and hybrid context
- candidate queues are prioritized for operator action instead of dumping raw adjacency noise
- automation is policy-aware, approval-aware, and rollback-aware
- the product can close a sales or release conversation with measurable proof

## Best-fit customers

- MSP teams managing many customer networks
- enterprise network operations teams
- hybrid infrastructure operations teams
- organizations that need evidence-backed automation rather than blind scripts

## Current proof points

- fixture-backed vendor support matrix
- synthetic validation matrix
- KPI readiness reporting
- real-device acceptance plan and checklist for final field validation

## Typical sales flow

1. start with Plug & Scan
2. pivot into topology layers
3. run path trace and diagnosis
4. show guarded change workflow
5. close with operational evidence

## Related docs

- `USER_GUIDE.md`
- `SALES_DEMO_PLAYBOOK.md`
- `VENDOR_SUPPORT_POLICY.md`
- `operational-validation/REAL_DEVICE_ACCEPTANCE_RUNBOOK.md`

## Free intake edition note

NetSphere can also be packaged as a `Free Intake Edition` focused on masked raw-output contribution for parser improvement.

In that edition:

- discovery, topology, diagnosis, and observability stay available
- raw output collection is restricted to an allowlisted read-only command set
- users review the sanitized preview before upload
- live change, rollback, privileged settings, and destructive automation remain blocked
