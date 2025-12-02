from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR}/fermentation.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


def _migrate_add_batch_id_to_readings(conn):
    """Add batch_id column to readings table if not present."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("readings")]
    if "batch_id" not in columns:
        conn.execute(text("ALTER TABLE readings ADD COLUMN batch_id INTEGER REFERENCES batches(id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_batch_id ON readings(batch_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_batch_timestamp ON readings(batch_id, timestamp)"))
        print("Migration: Added batch_id column to readings table")


async def init_db():
    """Initialize database with migrations.

    Order matters:
    1. Run migrations first (for existing DBs with data)
    2. Then create_all (for new tables/columns in fresh DBs)
    3. Then data migrations (copy tilts to devices)
    """
    async with engine.begin() as conn:
        # Step 1: Schema migrations for existing DBs
        await conn.run_sync(_migrate_add_original_gravity)
        await conn.run_sync(_migrate_create_devices_table)
        await conn.run_sync(_migrate_add_reading_columns)
        await conn.run_sync(_migrate_readings_nullable_tilt_id)

        # Step 2: Create any missing tables (includes new Style, Recipe, Batch tables)
        await conn.run_sync(Base.metadata.create_all)

        # Step 3: Migrations that depend on new tables existing
        await conn.run_sync(_migrate_add_batch_id_to_readings)  # Add this line (after batches table exists)
        await conn.run_sync(_migrate_add_batch_heater_columns)  # Add heater control columns to batches
        await conn.run_sync(_migrate_add_batch_id_to_control_events)  # Add batch_id to control_events
        await conn.run_sync(_migrate_add_paired_to_tilts_and_devices)  # Add paired field

        # Step 4: Data migrations
        await conn.run_sync(_migrate_tilts_to_devices)


def _migrate_add_original_gravity(conn):
    """Add original_gravity column to tilts table if not present."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Check if tilts table exists
    if "tilts" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("tilts")]
    if "original_gravity" not in columns:
        conn.execute(text("ALTER TABLE tilts ADD COLUMN original_gravity REAL"))
        print("Migration: Added original_gravity column to tilts table")


def _migrate_create_devices_table(conn):
    """Create devices table if it doesn't exist (without SQLAlchemy metadata)."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "devices" in inspector.get_table_names():
        return  # Table exists, will check data migration separately

    # Create devices table manually (not via create_all)
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            device_type TEXT NOT NULL DEFAULT 'tilt',
            name TEXT NOT NULL,
            display_name TEXT,
            beer_name TEXT,
            original_gravity REAL,
            native_gravity_unit TEXT DEFAULT 'sg',
            native_temp_unit TEXT DEFAULT 'f',
            calibration_type TEXT DEFAULT 'none',
            calibration_data TEXT,
            auth_token TEXT,
            last_seen TIMESTAMP,
            battery_voltage REAL,
            firmware_version TEXT,
            color TEXT,
            mac TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    print("Migration: Created devices table")


def _migrate_tilts_to_devices(conn):
    """Migrate existing tilts to devices table, preserving calibration offsets."""
    from sqlalchemy import text
    import json

    # Check if tilts table exists and has data
    try:
        result = conn.execute(text("SELECT COUNT(*) FROM tilts"))
        tilt_count = result.scalar()
    except Exception:
        # tilts table doesn't exist (fresh install)
        return

    if tilt_count == 0:
        return  # No tilts to migrate

    # Check if these tilts are already in devices
    result = conn.execute(text("""
        SELECT COUNT(*) FROM devices d
        WHERE EXISTS (SELECT 1 FROM tilts t WHERE t.id = d.id)
    """))
    migrated_count = result.scalar()

    if migrated_count >= tilt_count:
        print(f"Migration: Tilts already migrated ({migrated_count} devices)")
        return

    # Get tilts that need migration
    tilts_to_migrate = conn.execute(text("""
        SELECT id, color, mac, beer_name, original_gravity, last_seen
        FROM tilts
        WHERE id NOT IN (SELECT id FROM devices)
    """)).fetchall()

    # Check if calibration_points table exists
    try:
        has_calibration = conn.execute(text(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='calibration_points'"
        )).scalar() is not None
    except Exception:
        has_calibration = False

    for tilt in tilts_to_migrate:
        tilt_id = tilt[0]
        color = tilt[1]
        mac = tilt[2]
        beer_name = tilt[3]
        original_gravity = tilt[4]
        last_seen = tilt[5]

        # Calculate calibration offsets from CalibrationPoint table
        sg_offset = 0.0
        temp_offset = 0.0
        calibration_type = "none"

        if has_calibration:
            # Get SG calibration points for this tilt
            sg_points = conn.execute(text("""
                SELECT raw_value, actual_value FROM calibration_points
                WHERE tilt_id = :tilt_id AND type = 'sg'
                ORDER BY raw_value
            """), {"tilt_id": tilt_id}).fetchall()

            # Get temp calibration points for this tilt
            temp_points = conn.execute(text("""
                SELECT raw_value, actual_value FROM calibration_points
                WHERE tilt_id = :tilt_id AND type = 'temp'
                ORDER BY raw_value
            """), {"tilt_id": tilt_id}).fetchall()

            # Determine calibration type based on number of points
            # Use linear interpolation if 2+ points exist for either SG or temp
            has_multi_point = (len(sg_points) >= 2 or len(temp_points) >= 2)

            if has_multi_point:
                calibration_type = "linear"
            elif sg_points or temp_points:
                # Single point: calculate offset
                calibration_type = "offset"
                if sg_points:
                    sg_offset = sg_points[0][1] - sg_points[0][0]
                if temp_points:
                    temp_offset = temp_points[0][1] - temp_points[0][0]

        calibration_data = json.dumps({
            "sg_offset": round(sg_offset, 4),
            "temp_offset": round(temp_offset, 2),
            # Store full calibration points for linear interpolation
            "sg_points": [[p[0], p[1]] for p in sg_points] if has_calibration and sg_points else [],
            "temp_points": [[p[0], p[1]] for p in temp_points] if has_calibration and temp_points else [],
        })

        conn.execute(text("""
            INSERT INTO devices (
                id, device_type, name, color, mac, beer_name,
                original_gravity, calibration_type, calibration_data,
                last_seen, created_at
            ) VALUES (
                :id, 'tilt', :name, :color, :mac, :beer_name,
                :original_gravity, :calibration_type, :calibration_data,
                :last_seen, CURRENT_TIMESTAMP
            )
        """), {
            "id": tilt_id,
            "name": color or tilt_id,
            "color": color,
            "mac": mac,
            "beer_name": beer_name,
            "original_gravity": original_gravity,
            "calibration_type": calibration_type,
            "calibration_data": calibration_data,
            "last_seen": last_seen,
        })

    print(f"Migration: Migrated {len(tilts_to_migrate)} tilts to devices table (with calibration data)")


def _migrate_add_reading_columns(conn):
    """Add new columns to readings table for multi-hydrometer support."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Check if readings table exists
    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("readings")]

    new_columns = [
        ("device_id", "TEXT REFERENCES devices(id)"),
        ("device_type", "TEXT DEFAULT 'tilt'"),
        ("angle", "REAL"),
        ("battery_voltage", "REAL"),
        ("battery_percent", "INTEGER"),
        ("source_protocol", "TEXT DEFAULT 'ble'"),
        ("status", "TEXT DEFAULT 'valid'"),
        ("is_pre_filtered", "INTEGER DEFAULT 0"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in columns:
            try:
                conn.execute(text(f"ALTER TABLE readings ADD COLUMN {col_name} {col_def}"))
                print(f"Migration: Added {col_name} column to readings table")
            except Exception as e:
                # Column might already exist in some edge cases
                print(f"Migration: Skipping {col_name} - {e}")

    # Create index for device_id if it doesn't exist
    try:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_device_id ON readings(device_id)"))
    except Exception:
        pass  # Index might already exist


def _migrate_readings_nullable_tilt_id(conn):
    """Make tilt_id nullable in readings table for non-Tilt devices.

    SQLite doesn't support ALTER COLUMN, so we need to recreate the table.
    This migration checks if tilt_id is NOT NULL and recreates the table
    with tilt_id as nullable.
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    # Check if tilt_id is currently NOT NULL by looking at table info
    result = conn.execute(text("PRAGMA table_info(readings)"))
    columns_info = result.fetchall()

    # Find tilt_id column and check if it's NOT NULL (notnull=1)
    tilt_id_info = None
    for col in columns_info:
        if col[1] == "tilt_id":  # col[1] is column name
            tilt_id_info = col
            break

    if tilt_id_info is None:
        return  # No tilt_id column, nothing to migrate

    # col[3] is notnull flag (1 = NOT NULL, 0 = nullable)
    if tilt_id_info[3] == 0:
        print("Migration: tilt_id already nullable, skipping")
        return  # Already nullable

    print("Migration: Recreating readings table with nullable tilt_id...")

    # Step 1: Create new table with correct schema
    conn.execute(text("""
        CREATE TABLE readings_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tilt_id VARCHAR(50) REFERENCES tilts(id),
            device_id VARCHAR(100) REFERENCES devices(id),
            device_type VARCHAR(20) DEFAULT 'tilt',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            sg_raw REAL,
            sg_calibrated REAL,
            temp_raw REAL,
            temp_calibrated REAL,
            rssi INTEGER,
            battery_voltage REAL,
            battery_percent INTEGER,
            angle REAL,
            source_protocol VARCHAR(20) DEFAULT 'ble',
            status VARCHAR(20) DEFAULT 'valid',
            is_pre_filtered INTEGER DEFAULT 0
        )
    """))

    # Step 2: Copy data from old table
    conn.execute(text("""
        INSERT INTO readings_new (
            id, tilt_id, device_id, device_type, timestamp,
            sg_raw, sg_calibrated, temp_raw, temp_calibrated, rssi,
            battery_voltage, battery_percent, angle,
            source_protocol, status, is_pre_filtered
        )
        SELECT
            id, tilt_id, device_id, device_type, timestamp,
            sg_raw, sg_calibrated, temp_raw, temp_calibrated, rssi,
            battery_voltage, battery_percent, angle,
            source_protocol, status, is_pre_filtered
        FROM readings
    """))

    # Step 3: Drop old table
    conn.execute(text("DROP TABLE readings"))

    # Step 4: Rename new table
    conn.execute(text("ALTER TABLE readings_new RENAME TO readings"))

    # Step 5: Recreate indexes
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_tilt_timestamp ON readings(tilt_id, timestamp)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_device_timestamp ON readings(device_id, timestamp)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_timestamp ON readings(timestamp)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_tilt_id ON readings(tilt_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_device_id ON readings(device_id)"))

    print("Migration: Readings table recreated with nullable tilt_id")


def _migrate_add_batch_heater_columns(conn):
    """Add heater control columns to batches table if not present."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("batches")]

    new_columns = [
        ("heater_entity_id", "VARCHAR(100)"),
        ("temp_target", "REAL"),
        ("temp_hysteresis", "REAL"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in columns:
            try:
                conn.execute(text(f"ALTER TABLE batches ADD COLUMN {col_name} {col_def}"))
                print(f"Migration: Added {col_name} column to batches table")
            except Exception as e:
                print(f"Migration: Skipping {col_name} - {e}")

    # Add composite index for efficient querying of fermenting batches with heaters
    indexes = [idx["name"] for idx in inspector.get_indexes("batches")]
    if "ix_batch_fermenting_heater" not in indexes:
        try:
            conn.execute(text(
                "CREATE INDEX ix_batch_fermenting_heater ON batches (status, heater_entity_id)"
            ))
            print("Migration: Added ix_batch_fermenting_heater index to batches table")
        except Exception as e:
            print(f"Migration: Skipping index creation - {e}")

    # Add partial unique index to prevent heater conflicts at database level
    if "idx_fermenting_heater_unique" not in indexes:
        try:
            conn.execute(text(
                "CREATE UNIQUE INDEX idx_fermenting_heater_unique "
                "ON batches (heater_entity_id) "
                "WHERE status = 'fermenting' AND heater_entity_id IS NOT NULL"
            ))
            print("Migration: Added unique constraint for fermenting batch heaters")
        except Exception as e:
            print(f"Migration: Skipping unique heater index creation - {e}")

    # Add partial unique index to prevent device conflicts at database level
    if "idx_fermenting_device_unique" not in indexes:
        try:
            conn.execute(text(
                "CREATE UNIQUE INDEX idx_fermenting_device_unique "
                "ON batches (device_id) "
                "WHERE status = 'fermenting' AND device_id IS NOT NULL"
            ))
            print("Migration: Added unique constraint for fermenting batch devices")
        except Exception as e:
            print(f"Migration: Skipping unique device index creation - {e}")


def _migrate_add_batch_id_to_control_events(conn):
    """Add batch_id column to control_events table if not present."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "control_events" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("control_events")]

    if "batch_id" not in columns:
        try:
            conn.execute(text("ALTER TABLE control_events ADD COLUMN batch_id INTEGER"))
            print("Migration: Added batch_id column to control_events table")
        except Exception as e:
            print(f"Migration: Skipping batch_id column - {e}")


def _migrate_add_paired_to_tilts_and_devices(conn):
    """Add paired boolean field and paired_at timestamp to tilts and devices tables."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    # Migrate tilts table
    if "tilts" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("tilts")]
        if "paired" not in columns:
            conn.execute(text("ALTER TABLE tilts ADD COLUMN paired INTEGER DEFAULT 0"))
            print("Migration: Added paired column to tilts table")
        if "paired_at" not in columns:
            conn.execute(text("ALTER TABLE tilts ADD COLUMN paired_at TIMESTAMP"))
            print("Migration: Added paired_at column to tilts table")

        # Create index on paired field
        indexes = [idx["name"] for idx in inspector.get_indexes("tilts")]
        if "ix_tilts_paired" not in indexes:
            conn.execute(text("CREATE INDEX ix_tilts_paired ON tilts (paired)"))
            print("Migration: Added index on tilts.paired")

    # Migrate devices table
    if "devices" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("devices")]
        if "paired" not in columns:
            conn.execute(text("ALTER TABLE devices ADD COLUMN paired INTEGER DEFAULT 0"))
            print("Migration: Added paired column to devices table")
        if "paired_at" not in columns:
            conn.execute(text("ALTER TABLE devices ADD COLUMN paired_at TIMESTAMP"))
            print("Migration: Added paired_at column to devices table")

        # Create index on paired field
        indexes = [idx["name"] for idx in inspector.get_indexes("devices")]
        if "ix_devices_paired" not in indexes:
            conn.execute(text("CREATE INDEX ix_devices_paired ON devices (paired)"))
            print("Migration: Added index on devices.paired")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
