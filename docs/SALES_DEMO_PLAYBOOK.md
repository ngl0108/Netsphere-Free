# Sales Demo Playbook

This playbook packages the strongest NetSphere product story into a short operator-led demo.

## Goal

Show that NetSphere is not only a monitoring screen, but a multi-vendor network operations platform that can:

- discover and reflect topology
- explain routed and overlay paths
- guide safe changes with approval and rollback
- close with measurable operational evidence

## Recommended demo length

- short version: 12-15 minutes
- full version: 20-25 minutes

## Demo flow

### 1. Open with Plug & Scan

Show:

- discovery run
- automatic jump into topology
- candidate queue with priority badges

Talk track:

- "We are not drawing topology by hand."
- "The system ranks what needs operator attention instead of dumping raw neighbors."

### 2. Pivot into L3 / BGP / VXLAN / Hybrid visibility

Show:

- topology mode switch between L2, L3, BGP, VXLAN, and Hybrid
- BGP summary
- overlay summary
- cloud-linked view if hybrid data is available

Talk track:

- "The same graph can move from cable adjacency to routing intent and overlay context."

### 2.5. Demonstrate the interactive topology editor

Show:

- enable Manual Edit mode from the toolbar
- drag nodes and snap to grid
- create a group box and name it (e.g. "Server Room A")
- add a manual link between two nodes with custom color and dashed style
- right-click a node to show the context menu
- press Ctrl+Z to undo the last action, then Ctrl+Y to redo
- Shift+Click to multi-select several nodes, then move them together
- press Ctrl+S to save the layout

Talk track:

- "This is not a read-only graph. Your operators can organize the topology exactly how they think about the network."
- "Every visual change — drag, group, link — supports undo/redo just like a drawing tool."
- "The layout is saved per-user and reloads automatically next time."

### 3. Trace a real path

Show:

- path trace
- degraded segment highlight
- diagnosis verdict
- next-action guidance

Talk track:

- "We move from a visual path to a structured explanation without leaving the workflow."

### 4. Show safe automation instead of blind automation

Show:

- compliance report
- automation plan
- approval modal
- rollback and post-check metadata

Talk track:

- "Automation is gated, traceable, and rollback-aware."

### 5. Close with proof

Show:

- KPI readiness
- vendor support matrix
- synthetic validation report
- release evidence card
- real-device acceptance plan for target vendor family

Talk track:

- "The close is evidence, not a promise."
- "If you pick your target vendor family, we already have the acceptance checklist ready."

## Suggested scenario variants

### MSP

- start with discovery and multi-site visibility
- emphasize candidate queue, path trace, and operator efficiency

### Enterprise network ops

- emphasize L3/BGP/VXLAN visibility
- emphasize approval trace, rollback, and KPI evidence

### Security operations

- emphasize diagnosis, northbound delivery, and incident-linked automation

### Hybrid cloud

- emphasize hybrid topology and release evidence

## Pre-demo checklist

- frontend and backend reachable
- demo account verified
- topology data loaded
- one path trace target prepared
- one compliance/remediation target prepared
- release evidence and KPI cards refreshed

## Post-demo close

Offer these next steps:

1. target-vendor real-device acceptance run
2. 72h connector soak in staging
3. controlled pilot with limited write scope
