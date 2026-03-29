# NetSphere High Availability (HA) Infrastructure Guide

NetSphere supports an **Active-Standby** High Availability architecture to ensure business continuity in case of server failure.

## Architecture Overview

In HA mode, multiple NetSphere nodes (instances) run simultaneously, but only one node (the **Active Leader**) executes write operations and background tasks (polling, discovery). The other nodes remain in **Standby** mode, ready to take over if the leader fails.

Leader election is managed via a shared **PostgreSQL** database (Lease mechanism).

## Prerequisites

To enable HA, you must provide a shared infrastructure layer. You cannot use the embedded (containerized) database/redis for multi-node HA unless you configure one node to host them for all others (not recommended for true HA).

### 1. Shared Database (PostgreSQL 15+)
- All NetSphere nodes must connect to the **same** PostgreSQL database.
- **Recommendation:** Use a managed RDS (AWS Aurora, Google Cloud SQL) or a physical PostgreSQL Cluster with Patroni/Pgpool.
- **Connection String:** Ensure all nodes use the same `DATABASE_URL`.

### 2. Shared Message Broker (Redis 7+)
- All NetSphere nodes must connect to the **same** Redis instance.
- Used for Celery task queues and real-time event broadcasting.
- **Recommendation:** Use Redis Sentinel or a managed Redis Cluster.
- **Connection String:** Ensure all nodes use the same `REDIS_URL`.

### 3. Load Balancer (VIP)
- A Load Balancer (L4/L7) or Virtual IP (Keepalived) is required to route user traffic to the **Active** node.
- NetSphere provides a `/health` API that returns `200 OK` (Active) or `503 Service Unavailable` (Standby) which can be used by the Load Balancer health checks.
  - Health Check URL: `http://<NODE_IP>:8000/api/v1/health` (Backend) or `http://<NODE_IP>/api/v1/health` (Frontend proxy)

## Configuration Steps

On each NetSphere node (server), configure the `.env` file:

```bash
# Common Settings (Must be identical across nodes)
POSTGRES_USER=netsphere
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=netsphere
DATABASE_URL=postgresql://netsphere:secure_password@<SHARED_DB_IP>:5432/netsphere
REDIS_URL=redis://<SHARED_REDIS_IP>:6379/0

# HA Settings
HA_ENABLED=true
# Unique ID for each node (e.g., node-1, node-2)
HA_NODE_ID=node-1 
```

## Deployment Checklist

1. **Database:** Deploy shared PostgreSQL and create `netsphere` user/db.
2. **Redis:** Deploy shared Redis.
3. **Node 1:**
   - Install NetSphere.
   - Set `HA_NODE_ID=node-1` in `.env`.
   - Start services (`./install.sh`).
4. **Node 2:**
   - Install NetSphere.
   - Set `HA_NODE_ID=node-2` in `.env`.
   - Start services.
5. **Verify:**
   - Check logs: `docker compose logs -f backend`
   - One node should say: `[HA] Acquired lease. I am the LEADER.`
   - Other node should say: `[HA] Lease held by node-1. I am STANDBY.`

## Failover Behavior

- If **Node 1** (Leader) crashes or loses DB connectivity:
  - The lease expires (default 10 seconds).
  - **Node 2** detects expired lease and acquires it.
  - **Node 2** promotes itself to Leader and starts background services (Celery Beat).
  - **Failover Time:** Typically 10-15 seconds.
