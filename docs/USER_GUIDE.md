# NetSphere User Guide

This guide describes the main user-facing workflows for NetSphere.

## 1. What NetSphere is

NetSphere is a multi-vendor network operations platform that combines:

- discovery and inventory
- topology and path visibility
- compliance and controlled automation
- diagnostics and operational evidence

## 2. Main navigation areas

### Dashboard

Use the dashboard for:

- platform health
- operational KPI cards
- release evidence status
- high-level issue visibility

### Discovery

Use discovery to:

- launch Plug & Scan
- monitor scan progress
- review discovery KPI summaries
- move directly into topology after collection

### Topology

Use topology to:

- inspect L2 adjacency
- switch to L3, BGP, VXLAN, and Hybrid views
- review candidate links
- run path trace
- inspect link and node detail
- filter by site, cloud provider, account, or region
- compare topology snapshots and view diffs

#### Topology editor (Manual Edit Mode)

Enable **Manual Edit** from the toolbar to enter the layout editor workspace.
In edit mode you can customize every visual aspect of the topology map.

| Feature | Description |
|---------|-------------|
| **Node editing** | Change custom name, icon role (Core / Distribution / Access / WLC / Cloud / AP), font size, wrap mode, and resize via drag handles or exact pixel input |
| **Link editing** | Add manual links between any two nodes, choose kind (L2 / L3 / Hybrid / Manual), set color, thickness, curve type (Smooth / Step / Straight), line style (Solid / Dashed / Dotted), and label position |
| **Auto-link override** | Override the label, color, and style of auto-discovered links without changing the underlying topology data |
| **Link visibility** | Hide or show auto-discovered links |
| **Group boxes** | Create colored zone boxes, set label, fill color, border color, font size. Use **Fit to Children** or **Arrange Children** for automatic layout |
| **Canvas tools** | Resolve Overlaps, Snap to Grid, Tidy Canvas |
| **Snap grid** | Toggle snap-to-grid for precise node placement (24px grid) |

#### Keyboard shortcuts (edit mode only)

| Shortcut | Action |
|----------|--------|
| `Ctrl+Z` | Undo (restores node positions and manual edges) |
| `Ctrl+Y` or `Ctrl+Shift+Z` | Redo |
| `Ctrl+S` | Save layout to database |
| `Ctrl+A` | Select all nodes |
| `Delete` / `Backspace` | Delete selected manual group box or manual link |
| `Shift+Click` | Multi-select nodes (drag to move together, or group into a box) |
| `Escape` | Deselect all and close panels |

#### Right-click context menu

Right-click on any element in edit mode to access a context menu:

- **On a node**: Edit Node, Create Link From Here, Copy Node ID, and for manual groups: Fit to Children, Arrange Children, Delete
- **On a link**: Edit Link, Delete (manual links), Hide/Show (auto links)
- **On the canvas**: Undo/Redo, Add Group Box, Tidy Canvas, Resolve Overlaps, Save Layout

#### Layout management

- **Save / Load**: Layouts are stored per-user in the database and automatically loaded on next visit
- **Import / Export**: Download your layout as JSON for backup or sharing, or import a previously exported layout
- **Reset**: Revert to auto-generated layout at any time

### Devices and Sites

Use these pages to:

- browse inventory
- review device facts and status
- group devices by site
- confirm per-device support profile

### Config

Use the config area to:

- back up device configs
- prepare dry-run deploys
- review change plan and guard results
- submit approval-aware deployment

### Compliance

Use compliance to:

- review drift or rule violations
- inspect automation plans
- move into remediation and change execution

### Notifications and Automation

Use notifications to:

- review active alerts
- preview issue-linked automation
- execute or approve closed-loop actions

### Diagnosis

Use diagnosis to:

- inspect abnormal hops
- review structured verdicts
- follow next-action guidance
- inspect collected command plans and outputs

### Settings

Use settings to:

- manage users and roles
- configure licenses and HA behavior
- control release evidence automation
- manage webhook connectors and operational defaults

## 3. Common operator workflows

### Workflow A: Discovery to topology

1. Start discovery from the Discovery page.
2. Confirm the run completes.
3. Open topology directly from the result card.
4. Review candidate queue and act on actionable items first.

### Workflow B: Trace a failing path

1. Open the Topology page.
2. Select the relevant topology mode.
3. Run path trace for the source and destination.
4. Open diagnosis for degraded or failed segments.

### Workflow C: Compliance to safe change

1. Open a compliance report.
2. Review the automation plan.
3. Check whether the action is direct, approval-required, or blocked.
4. Verify post-check and rollback metadata before execution.

### Workflow D: Close with evidence

1. Open the Dashboard.
2. Review KPI readiness, vendor support, and release evidence.
3. Export or package the required reports when preparing sign-off.

## 4. Role expectations

### Viewer

- can review inventory, topology, dashboard, reports, and evidence
- cannot execute changes

### Operator

- can run discovery
- can use diagnosis and operational workflows
- can submit approval-requiring actions

### Admin

- can manage settings, users, licenses, HA, and release evidence policies
- can approve or execute guarded workflows depending on policy

## 5. Best practices

- use topology filters instead of trying to read all layers at once
- start with dry-run before live changes
- treat candidate queue as a prioritized backlog, not a raw event list
- use KPI and release evidence when presenting readiness to stakeholders

## 6. Troubleshooting

If discovery looks incomplete:

- verify device reachability and credentials
- review candidate backlog and low-confidence links

If path trace is unclear:

- switch topology mode to the most relevant layer
- open diagnosis to inspect structured evidence

If a change is blocked:

- inspect support policy, approval requirement, and rollback compatibility

If release evidence is warning or critical:

- review the failing gate and attached latest report

## 7. Related docs

- `README.md`
- `FEATURE_BROCHURE.md`
- `SALES_DEMO_PLAYBOOK.md`
- `AUTODISCOVERY_AUTOTOPOLOGY_RUNBOOK.md`
- `KPI_READINESS_RUNBOOK.md`

## 8. Free intake edition workflow

If you are using `Free Intake Edition`, use the product primarily for safe visibility and contribution:

1. Run discovery and review topology or device pages.
2. Open `Data Contribution`.
3. Capture or paste only allowlisted read-only command outputs.
4. Review the sanitized preview locally.
5. Upload only if the masked result is acceptable.

Free Intake Edition intentionally blocks:

- config deployment
- rollback execution
- privileged admin mutation flows
- destructive automation paths
