from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy import Engine, text

from app.core.field_encryption import get_fernet


def _has_column(conn, dialect: str, table: str, column: str) -> bool:
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})")).mappings().all()
        return any(r["name"] == column for r in rows)
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = :table AND column_name = :column
            """
        ),
        {"table": table, "column": column},
    ).first()
    return row is not None


def _index_exists(conn, dialect: str, index_name: str) -> bool:
    if dialect == "sqlite":
        row = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='index' AND name=:name"),
            {"name": index_name},
        ).first()
        return row is not None
    row = conn.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :name"),
        {"name": index_name},
    ).first()
    return row is not None


def _table_exists(conn, dialect: str, table: str) -> bool:
    if dialect == "sqlite":
        row = conn.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table},
        ).first()
        return row is not None
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = :table
            """
        ),
        {"table": table},
    ).first()
    return row is not None


def _chunked(values: Iterable[int], size: int = 200) -> Iterable[list[int]]:
    chunk = []
    for v in values:
        chunk.append(v)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _encrypt_value(value: str) -> str:
    token = get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"enc:{token}"


def _encrypt_table_columns(conn, dialect: str, table: str, id_col: str, columns: list[str]) -> None:
    existing = [c for c in columns if _has_column(conn, dialect, table, c)]
    if not existing:
        return

    select_sql = f"SELECT {id_col}, {', '.join(existing)} FROM {table}"
    rows = conn.execute(text(select_sql)).mappings().all()
    for r in rows:
        params = {id_col: r[id_col]}
        set_parts: list[str] = []
        for col in existing:
            v = r.get(col)
            if v is None or not isinstance(v, str) or v == "":
                continue
            if v == "********":
                continue
            if v.startswith("enc:"):
                continue
            set_parts.append(f"{col} = :{col}")
            params[col] = _encrypt_value(v)
        if set_parts:
            conn.execute(text(f"UPDATE {table} SET {', '.join(set_parts)} WHERE {id_col} = :{id_col}"), params)


def _cloud_sensitive_keys(provider: str) -> set[str]:
    p = str(provider or "").strip().lower()
    keys = {
        "secret_key",
        "client_secret",
        "service_account_json",
        "private_key",
        "session_token",
        "source_session_token",
        "external_id",
    }
    if p == "aws":
        keys |= {"access_key", "secret_key", "source_access_key", "source_secret_key"}
    if p == "azure":
        keys |= {"client_secret"}
    if p == "gcp":
        keys |= {"service_account_json"}
    if p in {"naver", "naver_cloud", "ncp"}:
        keys |= {"access_key", "secret_key"}
    return keys


def _encrypt_cloud_credentials(conn, dialect: str) -> None:
    if not _table_exists(conn, dialect, "cloud_accounts"):
        return
    if not _has_column(conn, dialect, "cloud_accounts", "credentials"):
        return

    rows = conn.execute(text("SELECT id, provider, credentials FROM cloud_accounts")).mappings().all()
    for r in rows:
        raw = r.get("credentials")
        payload: dict | None = None
        if isinstance(raw, dict):
            payload = dict(raw)
        elif isinstance(raw, str) and raw.strip():
            try:
                maybe = json.loads(raw)
                if isinstance(maybe, dict):
                    payload = maybe
            except Exception:
                payload = None

        if not payload:
            continue

        changed = False
        for key in _cloud_sensitive_keys(str(r.get("provider") or "")):
            value = payload.get(key)
            if value in (None, "", "********"):
                continue
            if isinstance(value, str) and value.startswith("enc:"):
                continue
            payload[key] = _encrypt_value(str(value))
            changed = True

        if not changed:
            continue

        cred_param = payload if dialect == "postgresql" else json.dumps(payload, ensure_ascii=False)
        conn.execute(
            text("UPDATE cloud_accounts SET credentials = :credentials WHERE id = :id"),
            {"id": int(r["id"]), "credentials": cred_param},
        )


def _safe_execute(conn, sql: str, params: dict | None = None) -> None:
    try:
        if getattr(getattr(conn, "dialect", None), "name", None) == "postgresql":
            with conn.begin_nested():
                if params:
                    conn.execute(text(sql), params)
                else:
                    conn.execute(text(sql))
            return
        if params:
            conn.execute(text(sql), params)
        else:
            conn.execute(text(sql))
    except Exception:
        pass


def _dedupe_links(conn) -> None:
    rows = conn.execute(
        text(
            """
            SELECT id, source_device_id, source_interface_name, target_device_id, target_interface_name
            FROM links
            """
        )
    ).mappings().all()

    keep_by_key = {}
    to_update = []
    to_delete = []

    for r in rows:
        a_id = r["source_device_id"]
        b_id = r["target_device_id"]
        a_intf = r["source_interface_name"] or ""
        b_intf = r["target_interface_name"] or ""

        if a_id is None or b_id is None:
            continue

        if a_id <= b_id:
            norm = (a_id, a_intf, b_id, b_intf)
        else:
            norm = (b_id, b_intf, a_id, a_intf)

        if (a_id, a_intf, b_id, b_intf) != norm:
            to_update.append((r["id"], *norm))

        existing_id = keep_by_key.get(norm)
        if existing_id is None:
            keep_by_key[norm] = r["id"]
        else:
            keep = min(existing_id, r["id"])
            drop = max(existing_id, r["id"])
            keep_by_key[norm] = keep
            to_delete.append(drop)

    for row_id, src_id, src_intf, dst_id, dst_intf in to_update:
        conn.execute(
            text(
                """
                UPDATE links
                SET source_device_id=:src_id,
                    source_interface_name=:src_intf,
                    target_device_id=:dst_id,
                    target_interface_name=:dst_intf
                WHERE id=:id
                """
            ),
            {
                "id": row_id,
                "src_id": src_id,
                "src_intf": src_intf,
                "dst_id": dst_id,
                "dst_intf": dst_intf,
            },
        )

    for chunk in _chunked(sorted(set(to_delete))):
        for row_id in chunk:
            conn.execute(text("DELETE FROM links WHERE id=:id"), {"id": row_id})


def _dedupe_discovered_devices(conn) -> None:
    rows = conn.execute(
        text(
            """
            SELECT id, job_id, ip_address
            FROM discovered_devices
            WHERE ip_address IS NOT NULL
            """
        )
    ).mappings().all()

    keep_by_key = {}
    to_delete = []
    for r in rows:
        key = (r["job_id"], r["ip_address"])
        existing_id = keep_by_key.get(key)
        if existing_id is None:
            keep_by_key[key] = r["id"]
        else:
            keep = min(existing_id, r["id"])
            drop = max(existing_id, r["id"])
            keep_by_key[key] = keep
            to_delete.append(drop)

    for chunk in _chunked(sorted(set(to_delete))):
        for row_id in chunk:
            conn.execute(text("DELETE FROM discovered_devices WHERE id=:id"), {"id": row_id})


def run_migrations(engine: Engine) -> None:
    dialect = engine.dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        return

    with engine.begin() as conn:
        has_profiles = _table_exists(conn, dialect, "snmp_credential_profiles")
        has_sites = _table_exists(conn, dialect, "sites")
        has_discovery_jobs = _table_exists(conn, dialect, "discovery_jobs")
        has_links = _table_exists(conn, dialect, "links")
        has_discovered_devices = _table_exists(conn, dialect, "discovered_devices")
        has_neighbor_candidates = _table_exists(conn, dialect, "topology_neighbor_candidates")
        has_devices = _table_exists(conn, dialect, "devices")
        has_system_settings = _table_exists(conn, dialect, "system_settings")
        has_system_metrics = _table_exists(conn, dialect, "system_metrics")
        has_interface_metrics = _table_exists(conn, dialect, "interface_metrics")
        has_event_logs = _table_exists(conn, dialect, "event_logs")
        has_interfaces = _table_exists(conn, dialect, "interfaces")
        has_issues = _table_exists(conn, dialect, "issues")
        has_config_backups = _table_exists(conn, dialect, "config_backups")
        has_compliance_rules = _table_exists(conn, dialect, "compliance_rules")
        has_compliance_reports = _table_exists(conn, dialect, "compliance_reports")
        has_topology_layout = _table_exists(conn, dialect, "topology_layout")
        has_users = _table_exists(conn, dialect, "users")
        has_audit_logs = _table_exists(conn, dialect, "audit_logs")
        has_ha_leases = _table_exists(conn, dialect, "ha_leases")

        # SaaS / Multi-tenant tables
        has_tenants = _table_exists(conn, dialect, "tenants")
        has_cloud_accounts = _table_exists(conn, dialect, "cloud_accounts")
        has_cloud_resources = _table_exists(conn, dialect, "cloud_resources")
        has_ip_intel_cache = _table_exists(conn, dialect, "ip_intel_cache")

        if not has_tenants:
            if dialect == "postgresql":
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS tenants (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR NOT NULL UNIQUE,
                            description VARCHAR,
                            plan_type VARCHAR DEFAULT 'free',
                            max_devices INTEGER DEFAULT 100,
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            updated_at TIMESTAMPTZ
                        )
                        """
                    )
                )
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenants_name ON tenants(name)"))
            else:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS tenants (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name VARCHAR NOT NULL UNIQUE,
                            description VARCHAR,
                            plan_type VARCHAR DEFAULT 'free',
                            max_devices INTEGER DEFAULT 100,
                            is_active INTEGER DEFAULT 1,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP
                        )
                        """
                    )
                )
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_tenants_name ON tenants(name)"))

        if not has_cloud_accounts:
            if dialect == "postgresql":
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS cloud_accounts (
                            id SERIAL PRIMARY KEY,
                            name VARCHAR NOT NULL,
                            provider VARCHAR NOT NULL,
                            credentials JSONB NOT NULL,
                            tenant_id INTEGER REFERENCES tenants(id),
                            is_active BOOLEAN DEFAULT TRUE,
                            last_synced_at TIMESTAMPTZ,
                            sync_status VARCHAR,
                            sync_message VARCHAR,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            updated_at TIMESTAMPTZ
                        )
                        """
                    )
                )
            else:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS cloud_accounts (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name VARCHAR NOT NULL,
                            provider VARCHAR NOT NULL,
                            credentials JSON NOT NULL,
                            tenant_id INTEGER REFERENCES tenants(id),
                            is_active INTEGER DEFAULT 1,
                            last_synced_at TIMESTAMP,
                            sync_status VARCHAR,
                            sync_message VARCHAR,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP
                        )
                        """
                    )
                )

        if not has_cloud_resources:
            if dialect == "postgresql":
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS cloud_resources (
                            id SERIAL PRIMARY KEY,
                            account_id INTEGER NOT NULL REFERENCES cloud_accounts(id) ON DELETE CASCADE,
                            resource_id VARCHAR NOT NULL,
                            resource_type VARCHAR NOT NULL,
                            name VARCHAR,
                            region VARCHAR,
                            cidr_block VARCHAR,
                            resource_metadata JSONB,
                            state VARCHAR,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            updated_at TIMESTAMPTZ
                        )
                        """
                    )
                )
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_cloud_resources_resource_id ON cloud_resources(resource_id)"))
            else:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS cloud_resources (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            account_id INTEGER NOT NULL REFERENCES cloud_accounts(id) ON DELETE CASCADE,
                            resource_id VARCHAR NOT NULL,
                            resource_type VARCHAR NOT NULL,
                            name VARCHAR,
                            region VARCHAR,
                            cidr_block VARCHAR,
                        resource_metadata JSON,
                            state VARCHAR,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP
                        )
                        """
                    )
                )
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_cloud_resources_resource_id ON cloud_resources(resource_id)"))

        if has_cloud_resources:
            if _has_column(conn, dialect, "cloud_resources", "resource_metadata") is False:
                if dialect == "postgresql":
                    _safe_execute(conn, "ALTER TABLE cloud_resources ADD COLUMN resource_metadata JSONB")
                else:
                    _safe_execute(conn, "ALTER TABLE cloud_resources ADD COLUMN resource_metadata JSON")
            if _has_column(conn, dialect, "cloud_resources", "metadata") and _has_column(conn, dialect, "cloud_resources", "resource_metadata"):
                _safe_execute(conn, "UPDATE cloud_resources SET resource_metadata = COALESCE(resource_metadata, metadata)")

        if not has_ip_intel_cache:
            if dialect == "postgresql":
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS ip_intel_cache (
                            id SERIAL PRIMARY KEY,
                            ip VARCHAR NOT NULL,
                            provider_guess VARCHAR,
                            asn VARCHAR,
                            as_name VARCHAR,
                            org_name VARCHAR,
                            source VARCHAR,
                            raw_json TEXT,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            updated_at TIMESTAMPTZ DEFAULT NOW()
                        )
                        """
                    )
                )
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_ip_intel_cache_ip ON ip_intel_cache(ip)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ip_intel_cache_provider ON ip_intel_cache(provider_guess)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ip_intel_cache_updated ON ip_intel_cache(updated_at)"))
            else:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS ip_intel_cache (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            ip VARCHAR NOT NULL,
                            provider_guess VARCHAR,
                            asn VARCHAR,
                            as_name VARCHAR,
                            org_name VARCHAR,
                            source VARCHAR,
                            raw_json TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                )
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_ip_intel_cache_ip ON ip_intel_cache(ip)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ip_intel_cache_provider ON ip_intel_cache(provider_guess)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ip_intel_cache_updated ON ip_intel_cache(updated_at)"))

        if has_users:
            if _has_column(conn, dialect, "users", "tenant_id") is False:
                conn.execute(text("ALTER TABLE users ADD COLUMN tenant_id INTEGER REFERENCES tenants(id)"))

        if has_devices:
            if _has_column(conn, dialect, "devices", "tenant_id") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN tenant_id INTEGER REFERENCES tenants(id)"))

        if not has_ha_leases:
            if dialect == "postgresql":
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS ha_leases (
                            key VARCHAR PRIMARY KEY,
                            owner_id VARCHAR NOT NULL,
                            acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            last_renewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            expires_at TIMESTAMPTZ NOT NULL
                        )
                        """
                    )
                )
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ha_leases_owner_id ON ha_leases(owner_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ha_leases_expires_at ON ha_leases(expires_at)"))
            else:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS ha_leases (
                            key VARCHAR PRIMARY KEY,
                            owner_id VARCHAR NOT NULL,
                            acquired_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            last_renewed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            expires_at TIMESTAMP NOT NULL
                        )
                        """
                    )
                )
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ha_leases_owner_id ON ha_leases(owner_id)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ha_leases_expires_at ON ha_leases(expires_at)"))

        if has_users:
            if _has_column(conn, dialect, "users", "mfa_enabled") is False:
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN"))
                    conn.execute(text("UPDATE users SET mfa_enabled = COALESCE(mfa_enabled, FALSE)"))
                else:
                    conn.execute(text("ALTER TABLE users ADD COLUMN mfa_enabled INTEGER"))
                    conn.execute(text("UPDATE users SET mfa_enabled = COALESCE(mfa_enabled, 0)"))
            if _has_column(conn, dialect, "users", "email_verified") is False:
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN"))
                    conn.execute(text("UPDATE users SET email_verified = COALESCE(email_verified, FALSE)"))
                else:
                    conn.execute(text("ALTER TABLE users ADD COLUMN email_verified INTEGER"))
                    conn.execute(text("UPDATE users SET email_verified = COALESCE(email_verified, 0)"))

        if has_audit_logs:
            if _has_column(conn, dialect, "audit_logs", "chain_prev_hash") is False:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN chain_prev_hash VARCHAR"))
            if _has_column(conn, dialect, "audit_logs", "chain_hash") is False:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN chain_hash VARCHAR"))
            if _has_column(conn, dialect, "audit_logs", "chain_alg") is False:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN chain_alg VARCHAR"))
            if _has_column(conn, dialect, "audit_logs", "chain_version") is False:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN chain_version INTEGER"))
                conn.execute(text("UPDATE audit_logs SET chain_version = COALESCE(chain_version, 1)"))

        if has_profiles:
            if _has_column(conn, dialect, "snmp_credential_profiles", "ssh_username") is False:
                conn.execute(text("ALTER TABLE snmp_credential_profiles ADD COLUMN ssh_username VARCHAR"))
            if _has_column(conn, dialect, "snmp_credential_profiles", "ssh_password") is False:
                conn.execute(text("ALTER TABLE snmp_credential_profiles ADD COLUMN ssh_password VARCHAR"))
            if _has_column(conn, dialect, "snmp_credential_profiles", "ssh_port") is False:
                conn.execute(text("ALTER TABLE snmp_credential_profiles ADD COLUMN ssh_port INTEGER"))
            if _has_column(conn, dialect, "snmp_credential_profiles", "enable_password") is False:
                conn.execute(text("ALTER TABLE snmp_credential_profiles ADD COLUMN enable_password VARCHAR"))
            if _has_column(conn, dialect, "snmp_credential_profiles", "device_type") is False:
                conn.execute(text("ALTER TABLE snmp_credential_profiles ADD COLUMN device_type VARCHAR"))

        if has_sites:
            if _has_column(conn, dialect, "sites", "snmp_profile_id") is False:
                conn.execute(text("ALTER TABLE sites ADD COLUMN snmp_profile_id INTEGER"))

        if has_discovery_jobs:
            if _has_column(conn, dialect, "discovery_jobs", "site_id") is False:
                conn.execute(text("ALTER TABLE discovery_jobs ADD COLUMN site_id INTEGER"))
            if _has_column(conn, dialect, "discovery_jobs", "snmp_profile_id") is False:
                conn.execute(text("ALTER TABLE discovery_jobs ADD COLUMN snmp_profile_id INTEGER"))

        if has_links:
            if _has_column(conn, dialect, "links", "protocol") is False:
                conn.execute(text("ALTER TABLE links ADD COLUMN protocol VARCHAR"))
            if _has_column(conn, dialect, "links", "confidence") is False:
                conn.execute(text("ALTER TABLE links ADD COLUMN confidence FLOAT"))
            if _has_column(conn, dialect, "links", "discovery_source") is False:
                conn.execute(text("ALTER TABLE links ADD COLUMN discovery_source VARCHAR"))
            if _has_column(conn, dialect, "links", "first_seen") is False:
                conn.execute(text("ALTER TABLE links ADD COLUMN first_seen TIMESTAMP"))
            if _has_column(conn, dialect, "links", "last_seen") is False:
                conn.execute(text("ALTER TABLE links ADD COLUMN last_seen TIMESTAMP"))

            if dialect == "postgresql":
                conn.execute(
                    text(
                        """
                        UPDATE links
                        SET protocol = COALESCE(protocol, 'UNKNOWN'),
                            confidence = COALESCE(confidence, 0.5),
                            discovery_source = COALESCE(discovery_source, 'ssh_neighbors'),
                            first_seen = COALESCE(first_seen, NOW()),
                            last_seen = COALESCE(last_seen, NOW())
                        """
                    )
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE links
                        SET protocol = COALESCE(protocol, 'UNKNOWN'),
                            confidence = COALESCE(confidence, 0.5),
                            discovery_source = COALESCE(discovery_source, 'ssh_neighbors'),
                            first_seen = COALESCE(first_seen, CURRENT_TIMESTAMP),
                            last_seen = COALESCE(last_seen, CURRENT_TIMESTAMP)
                        """
                    )
                )

            _dedupe_links(conn)

            if not _index_exists(conn, dialect, "uq_links_normalized"):
                conn.execute(
                    text(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS uq_links_normalized
                        ON links (source_device_id, source_interface_name, target_device_id, target_interface_name)
                        """
                    )
                )

        if has_discovered_devices:
            _dedupe_discovered_devices(conn)
            if not _index_exists(conn, dialect, "uq_discovered_devices_job_ip"):
                conn.execute(
                    text(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS uq_discovered_devices_job_ip
                        ON discovered_devices (job_id, ip_address)
                        """
                    )
                )

            if _has_column(conn, dialect, "discovered_devices", "sys_object_id") is False:
                conn.execute(text("ALTER TABLE discovered_devices ADD COLUMN sys_object_id VARCHAR"))
            if _has_column(conn, dialect, "discovered_devices", "sys_descr") is False:
                conn.execute(text("ALTER TABLE discovered_devices ADD COLUMN sys_descr TEXT"))
            if _has_column(conn, dialect, "discovered_devices", "vendor_confidence") is False:
                conn.execute(text("ALTER TABLE discovered_devices ADD COLUMN vendor_confidence FLOAT"))
            if _has_column(conn, dialect, "discovered_devices", "chassis_candidate") is False:
                conn.execute(text("ALTER TABLE discovered_devices ADD COLUMN chassis_candidate BOOLEAN"))
            if _has_column(conn, dialect, "discovered_devices", "issues") is False:
                conn.execute(text("ALTER TABLE discovered_devices ADD COLUMN issues TEXT"))
            if _has_column(conn, dialect, "discovered_devices", "evidence") is False:
                conn.execute(text("ALTER TABLE discovered_devices ADD COLUMN evidence TEXT"))

            if dialect == "postgresql":
                conn.execute(
                    text(
                        """
                        UPDATE discovered_devices
                        SET vendor_confidence = COALESCE(vendor_confidence, 0.0),
                            chassis_candidate = COALESCE(chassis_candidate, FALSE),
                            issues = COALESCE(issues, '[]'),
                            evidence = COALESCE(evidence, '{}')
                        """
                    )
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE discovered_devices
                        SET vendor_confidence = COALESCE(vendor_confidence, 0.0),
                            chassis_candidate = COALESCE(chassis_candidate, 0),
                            issues = COALESCE(issues, '[]'),
                            evidence = COALESCE(evidence, '{}')
                        """
                    )
                )

        if has_neighbor_candidates:
            if not _index_exists(conn, dialect, "uq_topology_neighbor_candidates_key"):
                conn.execute(
                    text(
                        """
                        CREATE UNIQUE INDEX IF NOT EXISTS uq_topology_neighbor_candidates_key
                        ON topology_neighbor_candidates (
                            source_device_id,
                            neighbor_name,
                            COALESCE(mgmt_ip,''),
                            COALESCE(local_interface,''),
                            COALESCE(remote_interface,'')
                        )
                        """
                    )
                )

        if has_devices:
            if _has_column(conn, dialect, "devices", "snmp_version") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN snmp_version VARCHAR"))
            if _has_column(conn, dialect, "devices", "snmp_port") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN snmp_port INTEGER"))
            if _has_column(conn, dialect, "devices", "snmp_v3_username") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN snmp_v3_username VARCHAR"))
            if _has_column(conn, dialect, "devices", "snmp_v3_security_level") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN snmp_v3_security_level VARCHAR"))
            if _has_column(conn, dialect, "devices", "snmp_v3_auth_proto") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN snmp_v3_auth_proto VARCHAR"))
            if _has_column(conn, dialect, "devices", "snmp_v3_auth_key") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN snmp_v3_auth_key VARCHAR"))
            if _has_column(conn, dialect, "devices", "snmp_v3_priv_proto") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN snmp_v3_priv_proto VARCHAR"))
            if _has_column(conn, dialect, "devices", "snmp_v3_priv_key") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN snmp_v3_priv_key VARCHAR"))
            if _has_column(conn, dialect, "devices", "management_state") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN management_state VARCHAR DEFAULT 'managed'"))
            if _has_column(conn, dialect, "devices", "management_reason") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN management_reason VARCHAR"))
            if _has_column(conn, dialect, "devices", "managed_since") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN managed_since TIMESTAMP"))
            if _has_column(conn, dialect, "devices", "management_priority_score") is False:
                conn.execute(text("ALTER TABLE devices ADD COLUMN management_priority_score FLOAT DEFAULT 0"))
            conn.execute(text("UPDATE devices SET management_state = COALESCE(management_state, 'managed')"))
            conn.execute(text("UPDATE devices SET management_priority_score = COALESCE(management_priority_score, 0)"))

        if has_discovery_jobs:
            if _has_column(conn, dialect, "discovery_jobs", "snmp_version") is False:
                conn.execute(text("ALTER TABLE discovery_jobs ADD COLUMN snmp_version VARCHAR"))
            if _has_column(conn, dialect, "discovery_jobs", "snmp_port") is False:
                conn.execute(text("ALTER TABLE discovery_jobs ADD COLUMN snmp_port INTEGER"))
            if _has_column(conn, dialect, "discovery_jobs", "snmp_v3_username") is False:
                conn.execute(text("ALTER TABLE discovery_jobs ADD COLUMN snmp_v3_username VARCHAR"))
            if _has_column(conn, dialect, "discovery_jobs", "snmp_v3_security_level") is False:
                conn.execute(text("ALTER TABLE discovery_jobs ADD COLUMN snmp_v3_security_level VARCHAR"))
            if _has_column(conn, dialect, "discovery_jobs", "snmp_v3_auth_proto") is False:
                conn.execute(text("ALTER TABLE discovery_jobs ADD COLUMN snmp_v3_auth_proto VARCHAR"))
            if _has_column(conn, dialect, "discovery_jobs", "snmp_v3_auth_key") is False:
                conn.execute(text("ALTER TABLE discovery_jobs ADD COLUMN snmp_v3_auth_key VARCHAR"))
            if _has_column(conn, dialect, "discovery_jobs", "snmp_v3_priv_proto") is False:
                conn.execute(text("ALTER TABLE discovery_jobs ADD COLUMN snmp_v3_priv_proto VARCHAR"))
            if _has_column(conn, dialect, "discovery_jobs", "snmp_v3_priv_key") is False:
                conn.execute(text("ALTER TABLE discovery_jobs ADD COLUMN snmp_v3_priv_key VARCHAR"))

        if has_devices and has_discovery_jobs:
            if dialect == "postgresql":
                conn.execute(
                    text(
                        """
                        UPDATE devices
                        SET snmp_version = COALESCE(snmp_version, 'v2c'),
                            snmp_port = COALESCE(snmp_port, 161)
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        UPDATE discovery_jobs
                        SET snmp_version = COALESCE(snmp_version, 'v2c'),
                            snmp_port = COALESCE(snmp_port, 161)
                        """
                    )
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE devices
                        SET snmp_version = COALESCE(snmp_version, 'v2c'),
                            snmp_port = COALESCE(snmp_port, 161)
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        UPDATE discovery_jobs
                        SET snmp_version = COALESCE(snmp_version, 'v2c'),
                            snmp_port = COALESCE(snmp_port, 161)
                        """
                    )
                )

        if has_devices:
            if _has_column(conn, dialect, "devices", "site_id") and not _index_exists(conn, dialect, "ix_devices_site_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_devices_site_id ON devices (site_id)"))
            if _has_column(conn, dialect, "devices", "owner_id") and not _index_exists(conn, dialect, "ix_devices_owner_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_devices_owner_id ON devices (owner_id)"))

        if has_interfaces:
            if _has_column(conn, dialect, "interfaces", "device_id") and not _index_exists(conn, dialect, "ix_interfaces_device_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_interfaces_device_id ON interfaces (device_id)"))

        if has_links:
            if _has_column(conn, dialect, "links", "source_device_id") and not _index_exists(conn, dialect, "ix_links_source_device_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_links_source_device_id ON links (source_device_id)"))
            if _has_column(conn, dialect, "links", "target_device_id") and not _index_exists(conn, dialect, "ix_links_target_device_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_links_target_device_id ON links (target_device_id)"))
            if (
                _has_column(conn, dialect, "links", "source_device_id")
                and _has_column(conn, dialect, "links", "target_device_id")
                and not _index_exists(conn, dialect, "ix_links_source_target")
            ):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_links_source_target ON links (source_device_id, target_device_id)"))

        if has_system_metrics:
            if _has_column(conn, dialect, "system_metrics", "device_id") and not _index_exists(conn, dialect, "ix_system_metrics_device_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_system_metrics_device_id ON system_metrics (device_id)"))
            if _has_column(conn, dialect, "system_metrics", "timestamp") and not _index_exists(conn, dialect, "ix_system_metrics_timestamp"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_system_metrics_timestamp ON system_metrics (timestamp)"))
            if (
                _has_column(conn, dialect, "system_metrics", "device_id")
                and _has_column(conn, dialect, "system_metrics", "timestamp")
                and not _index_exists(conn, dialect, "ix_system_metrics_device_ts")
            ):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_system_metrics_device_ts ON system_metrics (device_id, timestamp)"))

        if dialect == "postgresql":
            _safe_execute(conn, "CREATE EXTENSION IF NOT EXISTS timescaledb")
            if has_system_metrics:
                _safe_execute(
                    conn,
                    "SELECT create_hypertable('system_metrics','timestamp', if_not_exists => TRUE, migrate_data => TRUE)"
                )
                _safe_execute(
                    conn,
                    """
                    CREATE MATERIALIZED VIEW IF NOT EXISTS system_metrics_1m
                    WITH (timescaledb.continuous) AS
                    SELECT time_bucket('1 minute', timestamp) AS bucket,
                           device_id,
                           avg(cpu_usage) AS cpu_usage_avg,
                           avg(memory_usage) AS memory_usage_avg,
                           avg(traffic_in) AS traffic_in_avg,
                           avg(traffic_out) AS traffic_out_avg
                    FROM system_metrics
                    GROUP BY bucket, device_id
                    WITH NO DATA
                    """
                )
                _safe_execute(
                    conn,
                    """
                    CREATE MATERIALIZED VIEW IF NOT EXISTS system_metrics_5m
                    WITH (timescaledb.continuous) AS
                    SELECT time_bucket('5 minutes', timestamp) AS bucket,
                           device_id,
                           avg(cpu_usage) AS cpu_usage_avg,
                           avg(memory_usage) AS memory_usage_avg,
                           avg(traffic_in) AS traffic_in_avg,
                           avg(traffic_out) AS traffic_out_avg
                    FROM system_metrics
                    GROUP BY bucket, device_id
                    WITH NO DATA
                    """
                )
                _safe_execute(
                    conn,
                    """
                    CREATE MATERIALIZED VIEW IF NOT EXISTS system_metrics_1h
                    WITH (timescaledb.continuous) AS
                    SELECT time_bucket('1 hour', timestamp) AS bucket,
                           device_id,
                           avg(cpu_usage) AS cpu_usage_avg,
                           avg(memory_usage) AS memory_usage_avg,
                           avg(traffic_in) AS traffic_in_avg,
                           avg(traffic_out) AS traffic_out_avg
                    FROM system_metrics
                    GROUP BY bucket, device_id
                    WITH NO DATA
                    """
                )
                _safe_execute(conn, "CREATE INDEX IF NOT EXISTS ix_system_metrics_1m_device_bucket ON system_metrics_1m (device_id, bucket)")
                _safe_execute(conn, "CREATE INDEX IF NOT EXISTS ix_system_metrics_5m_device_bucket ON system_metrics_5m (device_id, bucket)")
                _safe_execute(conn, "CREATE INDEX IF NOT EXISTS ix_system_metrics_1h_device_bucket ON system_metrics_1h (device_id, bucket)")
                _safe_execute(
                    conn,
                    "SELECT add_continuous_aggregate_policy('system_metrics_1m', start_offset => INTERVAL '2 days', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_continuous_aggregate_policy('system_metrics_5m', start_offset => INTERVAL '7 days', end_offset => INTERVAL '5 minutes', schedule_interval => INTERVAL '5 minutes')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_continuous_aggregate_policy('system_metrics_1h', start_offset => INTERVAL '30 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '1 hour')"
                )
                _safe_execute(
                    conn,
                    "ALTER TABLE system_metrics SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_compression_policy('system_metrics', INTERVAL '1 day')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_retention_policy('system_metrics', INTERVAL '7 days')"
                )
                _safe_execute(
                    conn,
                    "ALTER MATERIALIZED VIEW system_metrics_1m SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id')"
                )
                _safe_execute(
                    conn,
                    "ALTER MATERIALIZED VIEW system_metrics_5m SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id')"
                )
                _safe_execute(
                    conn,
                    "ALTER MATERIALIZED VIEW system_metrics_1h SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_compression_policy('system_metrics_1m', INTERVAL '7 days')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_compression_policy('system_metrics_5m', INTERVAL '7 days')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_compression_policy('system_metrics_1h', INTERVAL '7 days')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_retention_policy('system_metrics_1m', INTERVAL '1 year')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_retention_policy('system_metrics_5m', INTERVAL '1 year')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_retention_policy('system_metrics_1h', INTERVAL '1 year')"
                )
            if has_interface_metrics:
                _safe_execute(
                    conn,
                    "SELECT create_hypertable('interface_metrics','timestamp', if_not_exists => TRUE, migrate_data => TRUE)"
                )
                _safe_execute(
                    conn,
                    """
                    CREATE MATERIALIZED VIEW IF NOT EXISTS interface_metrics_1m
                    WITH (timescaledb.continuous) AS
                    SELECT time_bucket('1 minute', timestamp) AS bucket,
                           device_id,
                           interface_name,
                           avg(traffic_in_bps) AS in_bps_avg,
                           avg(traffic_out_bps) AS out_bps_avg,
                           avg(in_errors_per_sec) AS in_err_avg,
                           avg(out_errors_per_sec) AS out_err_avg,
                           avg(in_discards_per_sec) AS in_discards_avg,
                           avg(out_discards_per_sec) AS out_discards_avg
                    FROM interface_metrics
                    GROUP BY bucket, device_id, interface_name
                    WITH NO DATA
                    """
                )
                _safe_execute(
                    conn,
                    """
                    CREATE MATERIALIZED VIEW IF NOT EXISTS interface_metrics_5m
                    WITH (timescaledb.continuous) AS
                    SELECT time_bucket('5 minutes', timestamp) AS bucket,
                           device_id,
                           interface_name,
                           avg(traffic_in_bps) AS in_bps_avg,
                           avg(traffic_out_bps) AS out_bps_avg,
                           avg(in_errors_per_sec) AS in_err_avg,
                           avg(out_errors_per_sec) AS out_err_avg,
                           avg(in_discards_per_sec) AS in_discards_avg,
                           avg(out_discards_per_sec) AS out_discards_avg
                    FROM interface_metrics
                    GROUP BY bucket, device_id, interface_name
                    WITH NO DATA
                    """
                )
                _safe_execute(
                    conn,
                    """
                    CREATE MATERIALIZED VIEW IF NOT EXISTS interface_metrics_1h
                    WITH (timescaledb.continuous) AS
                    SELECT time_bucket('1 hour', timestamp) AS bucket,
                           device_id,
                           interface_name,
                           avg(traffic_in_bps) AS in_bps_avg,
                           avg(traffic_out_bps) AS out_bps_avg,
                           avg(in_errors_per_sec) AS in_err_avg,
                           avg(out_errors_per_sec) AS out_err_avg,
                           avg(in_discards_per_sec) AS in_discards_avg,
                           avg(out_discards_per_sec) AS out_discards_avg
                    FROM interface_metrics
                    GROUP BY bucket, device_id, interface_name
                    WITH NO DATA
                    """
                )
                _safe_execute(conn, "CREATE INDEX IF NOT EXISTS ix_interface_metrics_1m_key ON interface_metrics_1m (device_id, interface_name, bucket)")
                _safe_execute(conn, "CREATE INDEX IF NOT EXISTS ix_interface_metrics_5m_key ON interface_metrics_5m (device_id, interface_name, bucket)")
                _safe_execute(conn, "CREATE INDEX IF NOT EXISTS ix_interface_metrics_1h_key ON interface_metrics_1h (device_id, interface_name, bucket)")
                _safe_execute(
                    conn,
                    "SELECT add_continuous_aggregate_policy('interface_metrics_1m', start_offset => INTERVAL '2 days', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_continuous_aggregate_policy('interface_metrics_5m', start_offset => INTERVAL '7 days', end_offset => INTERVAL '5 minutes', schedule_interval => INTERVAL '5 minutes')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_continuous_aggregate_policy('interface_metrics_1h', start_offset => INTERVAL '30 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '1 hour')"
                )
                _safe_execute(
                    conn,
                    "ALTER TABLE interface_metrics SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id, interface_name')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_compression_policy('interface_metrics', INTERVAL '1 day')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_retention_policy('interface_metrics', INTERVAL '7 days')"
                )
                _safe_execute(
                    conn,
                    "ALTER MATERIALIZED VIEW interface_metrics_1m SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id, interface_name')"
                )
                _safe_execute(
                    conn,
                    "ALTER MATERIALIZED VIEW interface_metrics_5m SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id, interface_name')"
                )
                _safe_execute(
                    conn,
                    "ALTER MATERIALIZED VIEW interface_metrics_1h SET (timescaledb.compress, timescaledb.compress_segmentby = 'device_id, interface_name')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_compression_policy('interface_metrics_1m', INTERVAL '7 days')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_compression_policy('interface_metrics_5m', INTERVAL '7 days')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_compression_policy('interface_metrics_1h', INTERVAL '7 days')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_retention_policy('interface_metrics_1m', INTERVAL '1 year')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_retention_policy('interface_metrics_5m', INTERVAL '1 year')"
                )
                _safe_execute(
                    conn,
                    "SELECT add_retention_policy('interface_metrics_1h', INTERVAL '1 year')"
                )

        if has_event_logs:
            if _has_column(conn, dialect, "event_logs", "device_id") and not _index_exists(conn, dialect, "ix_event_logs_device_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_event_logs_device_id ON event_logs (device_id)"))
            if _has_column(conn, dialect, "event_logs", "timestamp") and not _index_exists(conn, dialect, "ix_event_logs_timestamp"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_event_logs_timestamp ON event_logs (timestamp)"))
            if (
                _has_column(conn, dialect, "event_logs", "device_id")
                and _has_column(conn, dialect, "event_logs", "timestamp")
                and not _index_exists(conn, dialect, "ix_event_logs_device_ts")
            ):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_event_logs_device_ts ON event_logs (device_id, timestamp)"))

        if has_issues:
            if _has_column(conn, dialect, "issues", "device_id") and not _index_exists(conn, dialect, "ix_issues_device_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_issues_device_id ON issues (device_id)"))

        if has_config_backups:
            if _has_column(conn, dialect, "config_backups", "is_golden") is False:
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE config_backups ADD COLUMN is_golden BOOLEAN"))
                else:
                    conn.execute(text("ALTER TABLE config_backups ADD COLUMN is_golden INTEGER"))
            if _has_column(conn, dialect, "config_backups", "created_at") is False:
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE config_backups ADD COLUMN created_at TIMESTAMP"))
                else:
                    conn.execute(text("ALTER TABLE config_backups ADD COLUMN created_at TIMESTAMP"))
            if _has_column(conn, dialect, "config_backups", "device_id") and not _index_exists(conn, dialect, "ix_config_backups_device_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_config_backups_device_id ON config_backups (device_id)"))

        if has_compliance_rules:
            if _has_column(conn, dialect, "compliance_rules", "standard_id") and not _index_exists(conn, dialect, "ix_compliance_rules_standard_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_compliance_rules_standard_id ON compliance_rules (standard_id)"))

        if has_compliance_reports:
            if _has_column(conn, dialect, "compliance_reports", "device_id") and not _index_exists(conn, dialect, "ix_compliance_reports_device_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_compliance_reports_device_id ON compliance_reports (device_id)"))

        if has_topology_layout:
            if _has_column(conn, dialect, "topology_layout", "user_id") and not _index_exists(conn, dialect, "ix_topology_layout_user_id"):
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_topology_layout_user_id ON topology_layout (user_id)"))

        if has_devices:
            _encrypt_table_columns(
                conn,
                dialect,
                "devices",
                "id",
                ["snmp_community", "snmp_v3_auth_key", "snmp_v3_priv_key", "ssh_password", "enable_password"],
            )
        if has_profiles:
            _encrypt_table_columns(
                conn,
                dialect,
                "snmp_credential_profiles",
                "id",
                ["snmp_community", "snmp_v3_auth_key", "snmp_v3_priv_key", "ssh_password", "enable_password"],
            )
        if has_discovery_jobs:
            _encrypt_table_columns(
                conn,
                dialect,
                "discovery_jobs",
                "id",
                ["snmp_community", "snmp_v3_auth_key", "snmp_v3_priv_key"],
            )
        if has_system_settings:
            _encrypt_table_columns(conn, dialect, "system_settings", "id", ["value"])
        if has_cloud_accounts:
            _encrypt_cloud_credentials(conn, dialect)
