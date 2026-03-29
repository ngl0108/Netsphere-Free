# Free Intake Experience Policy

## Product intent

Free Intake Edition is an experience-first field edition for three product pillars:

1. Auto Discovery
2. Auto Topology
3. Connected NMS

Sanitized raw-output contribution is important, but it is a secondary workflow. Users should first experience the product value, then choose to contribute parser-improvement data.

## Same-codebase rule

The following surfaces must stay aligned with Pro and must not be reimplemented as separate Free-only forks:

- discovery workflows
- topology rendering and trace workflows
- device inventory and diagnosis workflows

Free Intake Edition can differ only in:

- destructive action policy
- privileged admin controls
- contribution consent and upload workflow

This means fixes and UX improvements in discovery, topology, and connected NMS must land in Free automatically through the same routes, components, and backend services.

## Free pillar matrix

| Pillar | Free state | What stays open | What stays blocked |
| --- | --- | --- | --- |
| Auto Discovery | Open | scan, seed crawl, discovery status, approve/ignore, KPI review | config push after discovery |
| Auto Topology | Open | topology refresh, snapshots, path trace, candidate queue, L2/L3/BGP/VXLAN views | fabric execution, policy push |
| Connected NMS | Open | inventory, device detail, diagnosis, notifications, observability, logs, audit | privileged admin mutation, external delivery |
| Contribution | Open | allowlisted capture, sanitize preview, upload | raw original persistence, full config upload |

## Free navigation policy

Allowed:

- dashboard
- devices and device detail
- sites
- topology
- diagnosis
- notifications
- wireless
- discovery
- automation hub
- observability
- system logs
- audit trail
- data contribution

Blocked:

- config deployment
- image rollout
- policy push
- fabric execution
- ZTP execution
- cloud bootstrap
- compliance remediation
- approval center
- settings
- user management

Automation Hub stays open in Free, but only as a navigation hub for discovery, topology, diagnosis, observability, and contribution. Network-changing automation actions remain blocked.

## Free mutation policy

Allowed mutations:

- auth login, refresh, logout, profile flows
- device registration and editing
- site registration and editing
- discovery execution and discovery approvals
- topology snapshots, layout saves, candidate queue actions, path trace
- diagnosis execution
- issue read and resolve actions
- data contribution sanitize and upload flows

Blocked mutations:

- user administration
- license install or revoke
- support restore
- config deploy and rollback
- automation run actions that can change network state
- cloud, fabric, image, policy, ZTP, intent admin flows
- observability toggle or other privileged admin-only mutations

## Experience CTA rule

Contribution prompts should appear after product value is visible:

- discovery results
- topology and path trace
- device detail and diagnosis

Data contribution must never be the first or only value proposition.
