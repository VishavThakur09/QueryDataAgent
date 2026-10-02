# here we make the logic of the send the and store the data in the postgres database

import os
import csv
import psycopg2
from psycopg2 import sql, errors
from dotenv import load_dotenv

load_dotenv()

# ─── DB CONFIG ────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "dbname":   os.getenv("database", "postgres"),
    "host":     os.getenv("host",     "localhost"),
    "user":     os.getenv("user",     "postgres"),
    "password": os.getenv("passward", ""),   # note: env key is 'passward' (matches .env)
    "port":     os.getenv("port",     "5432"),
}

# ─── DATA FILES ───────────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")

CSV_FILES = {
    "users":    os.path.join(DATA_DIR, "users.csv"),
    "vehicles": os.path.join(DATA_DIR, "vehicles.csv"),
    "rides":    os.path.join(DATA_DIR, "rides.csv"),
    "payments": os.path.join(DATA_DIR, "payments.csv"),
    "ratings":  os.path.join(DATA_DIR, "ratings.csv"),
}

# ─── TABLE DDL ────────────────────────────────────────────────────────────────
# Tables are defined in FK-safe order (parents before children)
CREATE_TABLES = [
    # 1. users
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id     VARCHAR(10)  PRIMARY KEY,
        name        VARCHAR(100) NOT NULL,
        email       VARCHAR(150) UNIQUE NOT NULL,
        phone       VARCHAR(15),
        city        VARCHAR(80),
        signup_date DATE,
        status      VARCHAR(20)
    );
    """,

    # 2. vehicles
    """
    CREATE TABLE IF NOT EXISTS vehicles (
        vehicle_id       VARCHAR(10)  PRIMARY KEY,
        registration_no  VARCHAR(20)  UNIQUE NOT NULL,
        vehicle_type     VARCHAR(30),
        model            VARCHAR(80),
        color            VARCHAR(30),
        manufacture_year INTEGER,
        driver_id        VARCHAR(20),
        seating_capacity INTEGER,
        status           VARCHAR(20)
    );
    """,

    # 3. rides  (depends on users + vehicles)
    """
    CREATE TABLE IF NOT EXISTS rides (
        ride_id          VARCHAR(10)  PRIMARY KEY,
        user_id          VARCHAR(10)  REFERENCES users(user_id)    ON DELETE SET NULL,
        vehicle_id       VARCHAR(10)  REFERENCES vehicles(vehicle_id) ON DELETE SET NULL,
        ride_datetime    TIMESTAMP,
        pickup_location  VARCHAR(100),
        drop_location    VARCHAR(100),
        ride_status      VARCHAR(20),
        distance_km      NUMERIC(8,2),
        duration_min     INTEGER,
        fare             NUMERIC(10,2)
    );
    """,

    # 4. payments  (depends on rides + users)
    """
    CREATE TABLE IF NOT EXISTS payments (
        payment_id       VARCHAR(10)  PRIMARY KEY,
        ride_id          VARCHAR(10)  REFERENCES rides(ride_id)    ON DELETE SET NULL,
        user_id          VARCHAR(10)  REFERENCES users(user_id)    ON DELETE SET NULL,
        payment_datetime TIMESTAMP,
        amount           NUMERIC(10,2),
        payment_method   VARCHAR(30),
        payment_status   VARCHAR(20),
        transaction_id   VARCHAR(30)  UNIQUE NOT NULL
    );
    """,

    # 5. ratings  (depends on rides + users + vehicles)
    """
    CREATE TABLE IF NOT EXISTS ratings (
        rating_id   VARCHAR(10)  PRIMARY KEY,
        ride_id     VARCHAR(10)  REFERENCES rides(ride_id)    ON DELETE SET NULL,
        user_id     VARCHAR(10)  REFERENCES users(user_id)    ON DELETE SET NULL,
        vehicle_id  VARCHAR(10)  REFERENCES vehicles(vehicle_id) ON DELETE SET NULL,
        rating      INTEGER      CHECK (rating BETWEEN 1 AND 5),
        review      TEXT,
        rating_date DATE
    );
    """,
]

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def get_connection():
    """Create and return a psycopg2 connection."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = False
        return conn
    except psycopg2.OperationalError as e:
        print(f"[ERROR] Could not connect to PostgreSQL: {e}")
        print("        Check your .env values (host / user / passward / database / port).")
        raise


def create_tables(conn: psycopg2.extensions.connection) -> None:
    """Create all tables if they don't already exist."""
    with conn.cursor() as cur:
        for ddl in CREATE_TABLES:
            cur.execute(ddl)
    conn.commit()
    print("[OK]  Tables created / verified.")


def _clean(value: str) -> str | None:
    """Return None for empty strings, else the stripped value."""
    v = value.strip()
    return None if v == "" else v


def load_csv(filepath: str) -> list[dict]:
    """Read a CSV file and return list of row dicts (empty strings → None)."""
    rows = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({k: _clean(v) for k, v in row.items()})
    return rows


# ─── UPSERT FUNCTIONS ─────────────────────────────────────────────────────────

def insert_users(cur, rows: list[dict]) -> int:
    query = """
        INSERT INTO users (user_id, name, email, phone, city, signup_date, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            name        = EXCLUDED.name,
            email       = EXCLUDED.email,
            phone       = EXCLUDED.phone,
            city        = EXCLUDED.city,
            signup_date = EXCLUDED.signup_date,
            status      = EXCLUDED.status;
    """
    count = 0
    for r in rows:
        cur.execute(query, (
            r["user_id"], r["name"], r["email"],
            r["phone"], r["city"], r["signup_date"], r["status"],
        ))
        count += 1
    return count


def insert_vehicles(cur, rows: list[dict]) -> int:
    query = """
        INSERT INTO vehicles
            (vehicle_id, registration_no, vehicle_type, model, color,
             manufacture_year, driver_id, seating_capacity, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (vehicle_id) DO UPDATE SET
            registration_no  = EXCLUDED.registration_no,
            vehicle_type     = EXCLUDED.vehicle_type,
            model            = EXCLUDED.model,
            color            = EXCLUDED.color,
            manufacture_year = EXCLUDED.manufacture_year,
            driver_id        = EXCLUDED.driver_id,
            seating_capacity = EXCLUDED.seating_capacity,
            status           = EXCLUDED.status;
    """
    count = 0
    for r in rows:
        cur.execute(query, (
            r["vehicle_id"], r["registration_no"], r["vehicle_type"],
            r["model"], r["color"],
            int(r["manufacture_year"]) if r["manufacture_year"] else None,
            r["driver_id"],
            int(r["seating_capacity"]) if r["seating_capacity"] else None,
            r["status"],
        ))
        count += 1
    return count


def insert_rides(cur, rows: list[dict]) -> int:
    query = """
        INSERT INTO rides
            (ride_id, user_id, vehicle_id, ride_datetime, pickup_location,
             drop_location, ride_status, distance_km, duration_min, fare)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ride_id) DO UPDATE SET
            user_id          = EXCLUDED.user_id,
            vehicle_id       = EXCLUDED.vehicle_id,
            ride_datetime    = EXCLUDED.ride_datetime,
            pickup_location  = EXCLUDED.pickup_location,
            drop_location    = EXCLUDED.drop_location,
            ride_status      = EXCLUDED.ride_status,
            distance_km      = EXCLUDED.distance_km,
            duration_min     = EXCLUDED.duration_min,
            fare             = EXCLUDED.fare;
    """
    count = 0
    for r in rows:
        cur.execute(query, (
            r["ride_id"], r["user_id"], r["vehicle_id"],
            r["ride_datetime"], r["pickup_location"], r["drop_location"],
            r["ride_status"],
            float(r["distance_km"]) if r["distance_km"] else 0.0,
            int(r["duration_min"]) if r["duration_min"] else None,
            float(r["fare"]) if r["fare"] else None,
        ))
        count += 1
    return count


def insert_payments(cur, rows: list[dict]) -> int:
    query = """
        INSERT INTO payments
            (payment_id, ride_id, user_id, payment_datetime, amount,
             payment_method, payment_status, transaction_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (payment_id) DO UPDATE SET
            ride_id          = EXCLUDED.ride_id,
            user_id          = EXCLUDED.user_id,
            payment_datetime = EXCLUDED.payment_datetime,
            amount           = EXCLUDED.amount,
            payment_method   = EXCLUDED.payment_method,
            payment_status   = EXCLUDED.payment_status,
            transaction_id   = EXCLUDED.transaction_id;
    """
    count = 0
    for r in rows:
        cur.execute(query, (
            r["payment_id"], r["ride_id"], r["user_id"],
            r["payment_datetime"],
            float(r["amount"]) if r["amount"] else None,
            r["payment_method"], r["payment_status"], r["transaction_id"],
        ))
        count += 1
    return count


def insert_ratings(cur, rows: list[dict]) -> int:
    query = """
        INSERT INTO ratings
            (rating_id, ride_id, user_id, vehicle_id, rating, review, rating_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (rating_id) DO UPDATE SET
            ride_id     = EXCLUDED.ride_id,
            user_id     = EXCLUDED.user_id,
            vehicle_id  = EXCLUDED.vehicle_id,
            rating      = EXCLUDED.rating,
            review      = EXCLUDED.review,
            rating_date = EXCLUDED.rating_date;
    """
    count = 0
    for r in rows:
        cur.execute(query, (
            r["rating_id"], r["ride_id"], r["user_id"], r["vehicle_id"],
            int(r["rating"]) if r["rating"] else None,
            r["review"], r["rating_date"],
        ))
        count += 1
    return count


# Maps table name → (CSV file key, insert function)
TABLE_PIPELINE = [
    ("users",    "users",    insert_users),
    ("vehicles", "vehicles", insert_vehicles),
    ("rides",    "rides",    insert_rides),
    ("payments", "payments", insert_payments),
    ("ratings",  "ratings",  insert_ratings),
]

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def feed():
    """
    Main entry-point.
    1. Connect to PostgreSQL.
    2. Create tables (idempotent).
    3. Load each CSV and upsert rows into its table.
    4. Print a summary.
    """
    print("\n══════════════════════════════════════════")
    print("  QueryDataAgent — Data Feed to PostgreSQL")
    print("══════════════════════════════════════════\n")

    # ── Step 1: connect ────────────────────────────────────────────────────────
    try:
        conn = get_connection()
        print(f"[OK]  Connected to '{DB_CONFIG['dbname']}' on {DB_CONFIG['host']}:{DB_CONFIG['port']}\n")
    except Exception:
        return   # error already printed inside get_connection()

    # ── Step 2: create tables ─────────────────────────────────────────────────
    try:
        create_tables(conn)
    except Exception as e:
        print(f"[ERROR] Failed to create tables: {e}")
        conn.close()
        return

    # ── Step 3: feed each CSV ─────────────────────────────────────────────────
    total_inserted = 0
    for table_name, csv_key, insert_fn in TABLE_PIPELINE:
        filepath = CSV_FILES[csv_key]

        # Check file exists
        if not os.path.exists(filepath):
            print(f"[SKIP]  '{filepath}' not found — skipping {table_name}.")
            continue

        # Load CSV rows
        try:
            rows = load_csv(filepath)
        except Exception as e:
            print(f"[ERROR] Reading {filepath}: {e} — skipping {table_name}.")
            continue

        if not rows:
            print(f"[WARN]  {filepath} is empty — skipping {table_name}.")
            continue

        # Insert rows inside a savepoint so one bad table doesn't kill others
        try:
            with conn.cursor() as cur:
                cur.execute("SAVEPOINT sp_feed;")
                count = insert_fn(cur, rows)
                conn.commit()
                total_inserted += count
                print(f"[OK]  {table_name:<12} → {count} rows upserted from {os.path.basename(filepath)}")
        except errors.ForeignKeyViolation as e:
            conn.rollback()
            print(f"[ERROR] FK violation in '{table_name}': {e.pgerror.splitlines()[0]}")
        except errors.UniqueViolation as e:
            conn.rollback()
            print(f"[ERROR] Unique violation in '{table_name}': {e.pgerror.splitlines()[0]}")
        except Exception as e:
            conn.rollback()
            print(f"[ERROR] Unexpected error in '{table_name}': {e}")

    # ── Step 4: summary ───────────────────────────────────────────────────────
    print(f"\n[DONE] Total rows upserted: {total_inserted}")
    print("══════════════════════════════════════════\n")

    conn.close()


if __name__ == "__main__":
    feed()
