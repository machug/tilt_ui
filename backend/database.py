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


def _migrate_add_ml_columns(conn):
    """Add ML output columns to readings table."""
    from sqlalchemy import inspect, text
    import logging
    inspector = inspect(conn)

    if "readings" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("readings")]

    if "sg_filtered" in columns:
        logging.info("ML columns already exist, skipping migration")
        return

    logging.info("Adding ML output columns to readings table")

    # Add ML columns
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN sg_filtered REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN temp_filtered REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN confidence REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN sg_rate REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN temp_rate REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN is_anomaly INTEGER DEFAULT 0
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN anomaly_score REAL
    """))
    conn.execute(text("""
        ALTER TABLE readings ADD COLUMN anomaly_reasons TEXT
    """))

    logging.info("ML columns added successfully")


async def _migrate_temps_fahrenheit_to_celsius(engine):
    """Convert all temperature data from Fahrenheit to Celsius."""
    from sqlalchemy import text
    import logging

    async with engine.begin() as conn:
        # Check if readings table exists using SQLite-specific query
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='readings'"
        ))
        if not result.fetchone():
            logging.info("Readings table doesn't exist yet, skipping temperature migration")
            return

        # Check if migration already applied by sampling a reading
        result = await conn.execute(text(
            "SELECT temp_raw FROM readings WHERE temp_raw IS NOT NULL LIMIT 1"
        ))
        row = result.fetchone()

        if not row:
            logging.info("No readings with temperature data, skipping migration")
            return

        if row[0] < 50:  # Already in Celsius (fermentation temps are 0-40°C)
            logging.info("Temperatures already in Celsius, skipping migration")
            return

        logging.info("Converting temperatures from Fahrenheit to Celsius")

        # Convert readings table
        await conn.execute(text("""
            UPDATE readings
            SET
                temp_raw = (temp_raw - 32) * 5.0 / 9.0,
                temp_calibrated = (temp_calibrated - 32) * 5.0 / 9.0
            WHERE temp_raw IS NOT NULL OR temp_calibrated IS NOT NULL
        """))

        # Convert calibration points (only if table exists)
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='calibration_points'"
        ))
        if result.fetchone():
            await conn.execute(text("""
                UPDATE calibration_points
                SET
                    raw_value = (raw_value - 32) * 5.0 / 9.0,
                    actual_value = (actual_value - 32) * 5.0 / 9.0
                WHERE type = 'temp'
            """))

        # Convert batch temperature fields (only if table exists)
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batches'"
        ))
        if result.fetchone():
            # Check if any batch has temperature values that need conversion (>50 = Fahrenheit)
            result = await conn.execute(text("""
                SELECT COUNT(*) FROM batches
                WHERE (temp_target IS NOT NULL AND temp_target > 50)
                   OR (temp_hysteresis IS NOT NULL AND temp_hysteresis > 50)
            """))
            count = result.scalar()

            if count > 0:
                logging.info(f"Converting {count} batch temperature fields from Fahrenheit to Celsius")
                await conn.execute(text("""
                    UPDATE batches
                    SET
                        temp_target = (temp_target - 32) * 5.0 / 9.0,
                        temp_hysteresis = (temp_hysteresis - 32) * 5.0 / 9.0
                    WHERE temp_target IS NOT NULL OR temp_hysteresis IS NOT NULL
                """))

        # Convert ambient_readings table (only if table exists)
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ambient_readings'"
        ))
        if result.fetchone():
            # Check if ambient temps need conversion (>50 = Fahrenheit, ambient is typically -20 to 40°C)
            result = await conn.execute(text("""
                SELECT COUNT(*) FROM ambient_readings
                WHERE temperature IS NOT NULL AND temperature > 50
            """))
            count = result.scalar()

            if count > 0:
                logging.info(f"Converting {count} ambient temperature readings from Fahrenheit to Celsius")
                await conn.execute(text("""
                    UPDATE ambient_readings
                    SET temperature = (temperature - 32) * 5.0 / 9.0
                    WHERE temperature IS NOT NULL
                """))

        logging.info("Temperature conversion complete")


async def init_db():
    """Initialize database with migrations.

    Order matters:
    1. Run migrations first (for existing DBs with data)
    2. Then create_all (for new tables/columns in fresh DBs)
    3. Then data migrations (copy tilts to devices)

    IMPORTANT: This function is not thread-safe. Run with a single worker
    during startup to avoid migration race conditions. After initial startup,
    multiple workers can safely access the database for read/write operations.
    """
    async with engine.begin() as conn:
        # Step 1: Schema migrations for existing DBs
        await conn.run_sync(_migrate_add_original_gravity)
        await conn.run_sync(_migrate_create_devices_table)
        await conn.run_sync(_migrate_add_reading_columns)
        await conn.run_sync(_migrate_readings_nullable_tilt_id)
        await conn.run_sync(_migrate_add_ml_columns)

        # Step 2: Create any missing tables (includes new Style, Recipe, Batch tables)
        await conn.run_sync(Base.metadata.create_all)

        # Step 3: Migrations that depend on new tables existing
        await conn.run_sync(_migrate_create_recipe_fermentables_table)  # Create recipe_fermentables table
        await conn.run_sync(_migrate_create_recipe_hops_table)  # Create recipe_hops table
        await conn.run_sync(_migrate_create_recipe_yeasts_table)  # Create recipe_yeasts table
        await conn.run_sync(_migrate_create_recipe_miscs_table)  # Create recipe_miscs table
        await conn.run_sync(_migrate_add_recipe_expanded_fields)  # Add expanded BeerXML fields to recipes
        await conn.run_sync(_migrate_add_batch_id_to_readings)  # Add this line (after batches table exists)
        await conn.run_sync(_migrate_add_batch_heater_columns)  # Add heater control columns to batches
        await conn.run_sync(_migrate_add_batch_id_to_control_events)  # Add batch_id to control_events
        await conn.run_sync(_migrate_add_paired_to_tilts_and_devices)  # Add paired field
        await conn.run_sync(_migrate_add_deleted_at)  # Add soft delete support to batches
        await conn.run_sync(_migrate_add_deleted_at_index)  # Add index on deleted_at column

    # Convert temperatures F→C (runs outside conn.begin() context since it has its own)
    await _migrate_temps_fahrenheit_to_celsius(engine)

    async with engine.begin() as conn:
        # Step 4: Data migrations
        await conn.run_sync(_migrate_tilts_to_devices)
        await conn.run_sync(_migrate_mark_outliers_invalid)  # Mark historical outliers

    # Add cooler support (runs outside conn.begin() context since it has its own)
    await _migrate_add_cooler_entity()


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

    # Create indexes if they don't exist
    try:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_device_id ON readings(device_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_readings_status ON readings(status)"))
    except Exception:
        pass  # Indexes might already exist


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


async def _migrate_add_cooler_entity():
    """Add cooler_entity_id column to batches table."""
    from sqlalchemy import text
    async with engine.begin() as conn:
        # Check if batches table exists
        result = await conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batches'"
        ))
        if not result.fetchone():
            return  # Fresh install, create_all will handle it

        # Check if column exists
        result = await conn.execute(text("PRAGMA table_info(batches)"))
        columns = {row[1] for row in result}

        if "cooler_entity_id" not in columns:
            await conn.execute(text(
                "ALTER TABLE batches ADD COLUMN cooler_entity_id VARCHAR(100)"
            ))
            print("Migration: Added cooler_entity_id column to batches table")


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


def _migrate_create_recipe_fermentables_table(conn):
    """Create recipe_fermentables table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_fermentables" in inspector.get_table_names():
        return  # Table exists

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_fermentables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(50),
            amount_kg REAL,
            yield_percent REAL,
            color_lovibond REAL,
            origin VARCHAR(50),
            supplier VARCHAR(100),
            notes TEXT,
            add_after_boil INTEGER DEFAULT 0,
            coarse_fine_diff REAL,
            moisture REAL,
            diastatic_power REAL,
            protein REAL,
            max_in_batch REAL,
            recommend_mash INTEGER
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fermentables_recipe ON recipe_fermentables(recipe_id)"))
    print("Migration: Created recipe_fermentables table")


def _migrate_create_recipe_hops_table(conn):
    """Create recipe_hops table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_hops" in inspector.get_table_names():
        return

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_hops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            alpha_percent REAL,
            amount_kg REAL NOT NULL,
            use VARCHAR(20) NOT NULL,
            time_min REAL,
            form VARCHAR(20),
            type VARCHAR(20),
            origin VARCHAR(50),
            substitutes VARCHAR(200),
            beta_percent REAL,
            hsi REAL,
            humulene REAL,
            caryophyllene REAL,
            cohumulone REAL,
            myrcene REAL,
            notes TEXT
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hops_recipe ON recipe_hops(recipe_id)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_hops_use ON recipe_hops(use)"))  # For dry hop queries
    print("Migration: Created recipe_hops table")


def _migrate_create_recipe_yeasts_table(conn):
    """Create recipe_yeasts table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_yeasts" in inspector.get_table_names():
        return

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_yeasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            lab VARCHAR(100),
            product_id VARCHAR(50),
            type VARCHAR(20),
            form VARCHAR(20),
            attenuation_percent REAL,
            temp_min_c REAL,
            temp_max_c REAL,
            flocculation VARCHAR(20),
            amount_l REAL,
            amount_kg REAL,
            add_to_secondary INTEGER DEFAULT 0,
            best_for TEXT,
            times_cultured INTEGER,
            max_reuse INTEGER,
            notes TEXT
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_yeasts_recipe ON recipe_yeasts(recipe_id)"))
    print("Migration: Created recipe_yeasts table")


def _migrate_create_recipe_miscs_table(conn):
    """Create recipe_miscs table if it doesn't exist."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipe_miscs" in inspector.get_table_names():
        return

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS recipe_miscs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            type VARCHAR(50) NOT NULL,
            use VARCHAR(20) NOT NULL,
            time_min REAL,
            amount_kg REAL,
            amount_is_weight INTEGER DEFAULT 1,
            use_for TEXT,
            notes TEXT
        )
    """))

    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_miscs_recipe ON recipe_miscs(recipe_id)"))
    print("Migration: Created recipe_miscs table")


def _migrate_add_recipe_expanded_fields(conn):
    """Add expanded BeerXML fields to recipes table."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "recipes" not in inspector.get_table_names():
        return

    columns = [c["name"] for c in inspector.get_columns("recipes")]

    new_columns = [
        ("brewer", "VARCHAR(100)"),
        ("asst_brewer", "VARCHAR(100)"),
        ("boil_size_l", "REAL"),
        ("boil_time_min", "INTEGER"),
        ("efficiency_percent", "REAL"),
        ("primary_age_days", "INTEGER"),
        ("primary_temp_c", "REAL"),
        ("secondary_age_days", "INTEGER"),
        ("secondary_temp_c", "REAL"),
        ("tertiary_age_days", "INTEGER"),
        ("tertiary_temp_c", "REAL"),
        ("age_days", "INTEGER"),
        ("age_temp_c", "REAL"),
        ("carbonation_vols", "REAL"),
        ("forced_carbonation", "INTEGER"),
        ("priming_sugar_name", "VARCHAR(50)"),
        ("priming_sugar_amount_kg", "REAL"),
        ("taste_notes", "TEXT"),
        ("taste_rating", "REAL"),
        ("date", "VARCHAR(50)"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in columns:
            conn.execute(text(f"ALTER TABLE recipes ADD COLUMN {col_name} {col_def}"))

    print("Migration: Added expanded BeerXML fields to recipes table")


def _migrate_mark_outliers_invalid(conn):
    """Mark historical outlier readings as invalid.

    This migration finds existing readings with physically impossible values
    and marks them as invalid so they're filtered from charts.

    Valid ranges:
    - SG: 0.500-1.200 (beer is typically 1.000-1.120)
    - Temp: 32-212°F (freezing to boiling)
    """
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "readings" not in inspector.get_table_names():
        return

    columns = [c["name"] for c in inspector.get_columns("readings")]
    if "status" not in columns:
        return  # Status column doesn't exist yet, skip

    # Mark SG outliers
    result = conn.execute(text("""
        UPDATE readings
        SET status = 'invalid'
        WHERE status = 'valid'
        AND (sg_calibrated < 0.500 OR sg_calibrated > 1.200)
    """))
    sg_count = result.rowcount

    # Mark temperature outliers
    result = conn.execute(text("""
        UPDATE readings
        SET status = 'invalid'
        WHERE status = 'valid'
        AND (temp_calibrated < 32.0 OR temp_calibrated > 212.0)
    """))
    temp_count = result.rowcount

    total = sg_count + temp_count
    if total > 0:
        print(f"Migration: Marked {total} outlier readings as invalid ({sg_count} SG, {temp_count} temp)")


def _migrate_add_deleted_at(conn):
    """Add deleted_at column to batches table and migrate archived status."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    columns = [c["name"] for c in inspector.get_columns("batches")]

    if "deleted_at" not in columns:
        print("Migration: Adding deleted_at column to batches table")
        conn.execute(text("ALTER TABLE batches ADD COLUMN deleted_at TIMESTAMP"))

        # Migrate any 'archived' status to 'completed'
        result = conn.execute(
            text("UPDATE batches SET status = 'completed' WHERE status = 'archived'")
        )
        updated = result.rowcount
        if updated > 0:
            print(f"Migration: Migrated {updated} batches from 'archived' to 'completed' status")

        print("Migration: deleted_at column added successfully")
    else:
        print("Migration: deleted_at column already exists, skipping")


def _migrate_add_deleted_at_index(conn):
    """Add index on deleted_at column for better query performance."""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)

    if "batches" not in inspector.get_table_names():
        return  # Fresh install, create_all will handle it

    # Check if index already exists
    indexes = inspector.get_indexes("batches")
    index_names = [idx["name"] for idx in indexes]

    if "ix_batches_deleted_at" not in index_names:
        print("Migration: Adding index on deleted_at column")
        conn.execute(text("CREATE INDEX ix_batches_deleted_at ON batches (deleted_at)"))
        print("Migration: deleted_at index added successfully")
    else:
        print("Migration: deleted_at index already exists, skipping")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
