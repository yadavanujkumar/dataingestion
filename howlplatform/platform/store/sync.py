from __future__ import annotations

import json
from typing import Any, Dict, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine
from .db import get_engine


def sync_brand_manifest(manifest: Dict[str, Any], engine: Optional[Engine] = None) -> None:
    """Upsert brand manifest into 'brands' table and sync rows into 'sources' table."""
    if engine is None:
        engine = get_engine()

    brand_id = manifest["brand_id"]
    version = manifest["manifest_version"]
    
    # Split into static manifest and learned half
    learned_keys = {"variant_lists", "product_roster", "launch_calendar", "rules"}
    static_part = {k: v for k, v in manifest.items() if k not in learned_keys}
    learned_part = {k: v for k, v in manifest.items() if k in learned_keys}

    manifest_json = json.dumps(static_part)
    learned_json = json.dumps(learned_part)

    with engine.begin() as conn:
        is_sqlite = engine.dialect.name == "sqlite"
        if is_sqlite:
            conn.execute(
                text("""
                    INSERT INTO brands (brand_id, manifest, learned, manifest_version, updated_at)
                    VALUES (:brand_id, :manifest, :learned, :version, CURRENT_TIMESTAMP)
                    ON CONFLICT(brand_id) DO UPDATE SET
                        manifest = excluded.manifest,
                        learned = excluded.learned,
                        manifest_version = excluded.manifest_version,
                        updated_at = CURRENT_TIMESTAMP
                """),
                {"brand_id": brand_id, "manifest": manifest_json, "learned": learned_json, "version": version}
            )
        else:
            conn.execute(
                text("""
                    INSERT INTO brands (brand_id, manifest, learned, manifest_version, updated_at)
                    VALUES (:brand_id, :manifest::jsonb, :learned::jsonb, :version, CURRENT_TIMESTAMP)
                    ON CONFLICT(brand_id) DO UPDATE SET
                        manifest = excluded.manifest,
                        learned = excluded.learned,
                        manifest_version = excluded.manifest_version,
                        updated_at = CURRENT_TIMESTAMP
                """),
                {"brand_id": brand_id, "manifest": manifest_json, "learned": learned_json, "version": version}
            )

        # Upsert sources
        for src in manifest.get("sources", []):
            source_id = src["source_id"]
            channel = src["channel"]
            domain = src["domain"]
            mode = src["mode"]
            schema_ref = src["schema_ref"]
            auth_status = src.get("auth_status", "active")
            config_json = json.dumps({
                "account_ref": src.get("account_ref"),
                "cadence": src.get("cadence"),
                "currency": src.get("currency"),
                "timezone": src.get("timezone"),
            })

            if is_sqlite:
                conn.execute(
                    text("""
                        INSERT INTO sources (source_id, brand_id, channel, domain, mode, schema_ref, auth_status, config, updated_at)
                        VALUES (:source_id, :brand_id, :channel, :domain, :mode, :schema_ref, :auth_status, :config, CURRENT_TIMESTAMP)
                        ON CONFLICT(source_id) DO UPDATE SET
                            channel = excluded.channel,
                            domain = excluded.domain,
                            mode = excluded.mode,
                            schema_ref = excluded.schema_ref,
                            auth_status = excluded.auth_status,
                            config = excluded.config,
                            updated_at = CURRENT_TIMESTAMP
                    """),
                    {
                        "source_id": source_id,
                        "brand_id": brand_id,
                        "channel": channel,
                        "domain": domain,
                        "mode": mode,
                        "schema_ref": schema_ref,
                        "auth_status": auth_status,
                        "config": config_json,
                    }
                )
            else:
                conn.execute(
                    text("""
                        INSERT INTO sources (source_id, brand_id, channel, domain, mode, schema_ref, auth_status, config, updated_at)
                        VALUES (:source_id, :brand_id, :channel, :domain, :mode, :schema_ref, :auth_status, :config::jsonb, CURRENT_TIMESTAMP)
                        ON CONFLICT(source_id) DO UPDATE SET
                            channel = excluded.channel,
                            domain = excluded.domain,
                            mode = excluded.mode,
                            schema_ref = excluded.schema_ref,
                            auth_status = excluded.auth_status,
                            config = excluded.config,
                            updated_at = CURRENT_TIMESTAMP
                    """),
                    {
                        "source_id": source_id,
                        "brand_id": brand_id,
                        "channel": channel,
                        "domain": domain,
                        "mode": mode,
                        "schema_ref": schema_ref,
                        "auth_status": auth_status,
                        "config": config_json,
                    }
                )
