import os
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.field_encryption import get_fernet, make_fernet

logger = logging.getLogger(__name__)


def _encrypt_value(value: str) -> str:
    token = get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"enc:{token}"


def _decrypt_with_old_key(value: str) -> str | None:
    raw_old = (os.getenv("OLD_FIELD_ENCRYPTION_KEY") or "").strip()
    if not raw_old:
        return None
    if not isinstance(value, str) or not value.startswith("enc:"):
        return None
    token = value[4:]
    try:
        return make_fernet(raw_old).decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    dry_run = os.getenv("DRY_RUN", "1") not in {"0", "false", "False", "no", "NO"}

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        updates = 0

        def reencrypt_table(table: str, cols: list[str]) -> None:
            nonlocal updates
            rows = session.execute(text(f"SELECT id, {', '.join(cols)} FROM {table}")).mappings().all()
            for r in rows:
                set_parts = []
                params = {"id": r["id"]}
                for col in cols:
                    v = r.get(col)
                    if v is None or not isinstance(v, str) or v == "":
                        continue
                    if v == "********":
                        continue
                    if v.startswith("enc:"):
                        plain = _decrypt_with_old_key(v)
                        if plain is None:
                            continue
                        set_parts.append(f"{col} = :{col}")
                        params[col] = _encrypt_value(plain)
                        continue
                    set_parts.append(f"{col} = :{col}")
                    params[col] = _encrypt_value(v)
                if set_parts:
                    updates += 1
                    if not dry_run:
                        session.execute(text(f"UPDATE {table} SET {', '.join(set_parts)} WHERE id = :id"), params)

        reencrypt_table(
            "devices",
            ["snmp_community", "snmp_v3_auth_key", "snmp_v3_priv_key", "ssh_password", "enable_password"],
        )

        reencrypt_table(
            "snmp_credential_profiles",
            ["snmp_community", "snmp_v3_auth_key", "snmp_v3_priv_key", "ssh_password", "enable_password"],
        )
        reencrypt_table("discovery_jobs", ["snmp_community", "snmp_v3_auth_key", "snmp_v3_priv_key"])
        reencrypt_table("system_settings", ["value"])

        if not dry_run:
            session.commit()

        logger.info("reencrypt_credentials rows_updated=%s dry_run=%s", updates, dry_run)
    finally:
        session.close()


if __name__ == "__main__":
    main()
