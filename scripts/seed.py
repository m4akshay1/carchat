"""Rebuild the CarChat database from scratch.

    python scripts/seed.py

What it does, in order:
  1. Applies db/schema.sql (drops and recreates the table and both views).
  2. Creates the two read-only database users and grants each one SELECT
     on its own view only.
  3. Loads about 300 vehicles.

Real vs generated data:
  - REAL, from the public EPA fuel economy dataset (fueleconomy.gov):
    year, make, model, trim text, drive, fuel type, combined MPG, and the
    EPA size class that body_style is mapped from.
  - GENERATED: stock number, VIN, condition, mileage, colour, list price,
    cost, date in stock, status and store. No real dealership's data is used.

Uses ADMIN_DATABASE_URL, which is for local/setup use only and is never
deployed with the app.
"""

from __future__ import annotations

import csv
import os
import random
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

ROOT = Path(__file__).resolve().parent.parent
EPA_URL = "https://www.fueleconomy.gov/feg/epadata/vehicles.csv"
EPA_CSV = ROOT / "data" / "vehicles.csv"

ROW_COUNT = 300
FIRST_STOCK_NUMBER = 10300  # KG10300 .. KG10599
STORES = ["Demo Motors North", "Demo Motors Central", "Demo Motors South"]

# Mainstream makes a volume dealership group would actually stock.
MAKES = {
    "Ford", "Toyota", "Honda", "Chevrolet", "Nissan", "Hyundai", "Kia", "Jeep",
    "Ram", "GMC", "Subaru", "Volkswagen", "Mazda", "Buick", "Dodge", "Chrysler",
}

BODY_STYLE_WEIGHTS = {"suv": 40, "truck": 25, "sedan": 25, "van": 5, "coupe": 5}
NEW_BASE_PRICE = {"truck": 52000, "suv": 44000, "sedan": 31000, "van": 43000, "coupe": 46000}
COLORS = ["white", "black", "silver", "gray", "blue", "red", "green", "brown", "orange"]
COLOR_WEIGHTS = [24, 20, 14, 16, 10, 9, 3, 2, 2]
DRIVE = {
    "Front-Wheel Drive": "FWD",
    "Rear-Wheel Drive": "RWD",
    "All-Wheel Drive": "AWD",
    "4-Wheel Drive": "4WD",
    "Part-time 4-Wheel Drive": "4WD",
}
FUEL = {"": "gasoline", "FFV": "gasoline", "Diesel": "diesel", "Hybrid": "hybrid",
        "Plug-in Hybrid": "plug-in hybrid", "EV": "electric"}
VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"  # real VINs never use I, O or Q


def body_style(epa_class: str) -> str | None:
    """Map an EPA size class to one of our five body styles (None = skip)."""
    if "Pickup" in epa_class:
        return "truck"
    if "Sport Utility" in epa_class:
        return "suv"
    if "Van" in epa_class or "Minivan" in epa_class:
        return "van"
    if epa_class in ("Two Seaters", "Minicompact Cars"):
        return "coupe"
    if epa_class in ("Subcompact Cars", "Compact Cars", "Midsize Cars", "Large Cars"):
        return "sedan"
    return None  # station wagons and special purpose vehicles are left out


def load_epa() -> dict[str, list[dict]]:
    """Return real EPA vehicle records for 2015-2027, grouped by body style."""
    if not EPA_CSV.exists():
        EPA_CSV.parent.mkdir(exist_ok=True)
        print(f"Downloading {EPA_URL} ...")
        urllib.request.urlretrieve(EPA_URL, EPA_CSV)

    by_style: dict[str, list[dict]] = {style: [] for style in BODY_STYLE_WEIGHTS}
    with open(EPA_CSV, newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            if not row["year"].isdigit() or not 2015 <= int(row["year"]) <= 2027:
                continue
            style = body_style(row["VClass"])
            if style is None or row["make"] not in MAKES:
                continue
            if row["drive"] not in DRIVE or row["atvType"] not in FUEL:
                continue
            base = row["baseModel"] or row["model"]
            trim = row["model"][len(base):].strip() if row["model"].startswith(base) else ""
            mpg = int(row["comb08"]) if row["comb08"].isdigit() and int(row["comb08"]) > 0 else None
            by_style[style].append({
                "year": int(row["year"]),
                "make": row["make"],
                "model": base,
                "trim": trim or None,
                "body_style": style,
                "drive": DRIVE[row["drive"]],
                "fuel_type": FUEL[row["atvType"]],
                "combined_mpg": mpg,
            })
    return by_style


def generate_vehicles(by_style: dict[str, list[dict]], today: date) -> list[dict]:
    """Pick real EPA vehicles and attach generated lot details. Fixed seed."""
    rng = random.Random(42)
    styles = list(BODY_STYLE_WEIGHTS)
    weights = list(BODY_STYLE_WEIGHTS.values())
    vehicles = []
    for i in range(ROW_COUNT):
        # A lot skews recent: weight newer model years more heavily.
        pool = by_style[rng.choices(styles, weights)[0]]
        recency = [3 if today.year - r["year"] <= 1 else 2 if today.year - r["year"] <= 4 else 1 for r in pool]
        v = dict(rng.choices(pool, recency)[0])
        age = max(0, today.year - v["year"])

        # Condition and mileage follow from the vehicle's age.
        if age == 0:
            condition = "new" if rng.random() < 0.9 else "used"
        elif age == 1:
            condition = "new" if rng.random() < 0.25 else "used"
        else:
            condition = "used"
        if condition == "new":
            mileage = rng.randint(3, 150)
        else:
            mileage = int(max(age, 1) * rng.uniform(8000, 14000) + rng.uniform(0, 5000))
            if age <= 5 and mileage < 60000 and rng.random() < 0.45:
                condition = "certified"

        # Days on lot: mostly fresh, with a deliberate tail past 60 and 90 days
        # so that aging questions return results.
        bucket = rng.choices([(0, 30), (31, 60), (61, 90), (91, 210)], [50, 22, 15, 13])[0]
        days_on_lot = rng.randint(*bucket)

        # Price: a new-vehicle base for the body style, depreciated by age.
        price = NEW_BASE_PRICE[v["body_style"]] * rng.uniform(0.75, 1.25)
        if condition != "new":
            price *= 0.91 ** max(age, 1) * rng.uniform(0.9, 1.05)
        list_price = max(5995, round(price / 500) * 500 - 5)

        # Cost: usually below list price; stale units are sometimes underwater.
        cost_ratio = rng.uniform(0.80, 0.96)
        if days_on_lot > 120 and rng.random() < 0.2:
            cost_ratio = rng.uniform(1.01, 1.05)
        cost = round(list_price * cost_ratio / 50) * 50

        v.update({
            "stock_number": f"KG{FIRST_STOCK_NUMBER + i}",
            "vin": "".join(rng.choice(VIN_CHARS) for _ in range(17)),
            "condition": condition,
            "mileage": mileage,
            "exterior_color": rng.choices(COLORS, COLOR_WEIGHTS)[0],
            "list_price": list_price,
            "cost": cost,
            "date_in_stock": today - timedelta(days=days_on_lot),
            "status": rng.choices(["available", "sale_pending", "sold"], [78, 10, 12])[0],
            "store": rng.choice(STORES),
        })
        vehicles.append(v)
    return vehicles


def create_reader(conn: psycopg.Connection, db_url: str, view: str) -> str:
    """Create (or reset) a login that can SELECT from one view and nothing else.

    The user name and password come from the app's own connection string, so
    the app and the database always agree and nothing secret is in the repo.
    """
    info = conninfo_to_dict(db_url)
    user, password, dbname = info["user"], info["password"], info["dbname"]
    role = sql.Identifier(user)

    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,)).fetchone()
    verb = "ALTER" if exists else "CREATE"
    conn.execute(sql.SQL(verb + " ROLE {} LOGIN PASSWORD {}").format(role, sql.Literal(password)))

    # Start from nothing, then grant exactly one thing.
    conn.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(role))
    conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(dbname), role))
    conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
    conn.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(sql.Identifier(view), role))

    # Belt and braces, enforced by the database for every session of this user.
    conn.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role))
    conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '3s'").format(role))
    return user


def main() -> None:
    load_dotenv(ROOT / ".env")
    try:
        admin_url = os.environ["ADMIN_DATABASE_URL"]
        sales_url = os.environ["DATABASE_URL_SALES"]
        gm_url = os.environ["DATABASE_URL_GM"]
    except KeyError as missing:
        sys.exit(f"Missing environment variable {missing}. Copy .env.example to .env and fill it in.")

    vehicles = generate_vehicles(load_epa(), date.today())
    columns = list(vehicles[0])

    with psycopg.connect(admin_url) as conn:
        conn.execute((ROOT / "db" / "schema.sql").read_text())
        # No one but the owner may create objects in the schema.
        conn.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        sales_user = create_reader(conn, sales_url, "inventory_view")
        gm_user = create_reader(conn, gm_url, "inventory_gm_view")

        insert = sql.SQL("INSERT INTO vehicles ({}) VALUES ({})").format(
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join(sql.Placeholder(c) for c in columns),
        )
        with conn.cursor() as cur:
            cur.executemany(insert, vehicles)

    print(f"Loaded {len(vehicles)} vehicles across {len(STORES)} stores.")
    print(f"Read-only users: {sales_user} -> inventory_view, {gm_user} -> inventory_gm_view")


if __name__ == "__main__":
    main()
