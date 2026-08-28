"""Generate synthetic analytics dataset with a planted refund anomaly."""

from __future__ import annotations

import os
import random
from datetime import date, timedelta

import psycopg
from psycopg.rows import dict_row

# Planted anomaly: North region refund spike in June 2025
ANOMALY_REGION = "North"
ANOMALY_MONTH = date(2025, 6, 1)
ANOMALY_REFUND_COUNT = 850

REGIONS = ["North", "South", "East", "West", "Central"]
REFUND_REASONS = [
    "defective product",
    "wrong item shipped",
    "customer changed mind",
    "duplicate order",
    "late delivery",
]

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://insightops:insightops@localhost:5432/insightops"
)


def seed_regions(cur) -> dict[str, int]:
    region_ids = {}
    for name in REGIONS:
        cur.execute(
            "INSERT INTO analytics.regions (name) VALUES (%s) ON CONFLICT (name) DO UPDATE SET name=EXCLUDED.name RETURNING region_id",
            (name,),
        )
        region_ids[name] = cur.fetchone()[0]
    return region_ids


def seed_customers(cur, region_ids: dict[str, int], count: int = 5000) -> list[int]:
    customer_ids = []
    for i in range(count):
        region = random.choice(REGIONS)
        is_test = random.random() < 0.05
        cur.execute(
            "INSERT INTO analytics.customers (name, email, region_id, is_test) VALUES (%s, %s, %s, %s) RETURNING customer_id",
            (f"Customer {i:05d}", f"customer{i}@example.com", region_ids[region], is_test),
        )
        customer_ids.append(cur.fetchone()[0])
    return customer_ids


def seed_orders(cur, customer_ids: list[int], region_ids: dict[str, int]) -> list[int]:
    order_ids = []
    start = date(2024, 1, 1)
    end = date(2025, 12, 31)
    current = start
    batch = []

    while current <= end:
        daily_orders = random.randint(60, 90)
        for _ in range(daily_orders):
            cid = random.choice(customer_ids)
            cur.execute("SELECT region_id FROM analytics.customers WHERE customer_id = %s", (cid,))
            rid = cur.fetchone()[0]
            amount = round(random.uniform(25.0, 500.0), 2)
            batch.append((cid, rid, amount, current))
            if len(batch) >= 1000:
                cur.executemany(
                    "INSERT INTO analytics.orders (customer_id, region_id, amount, order_date) VALUES (%s, %s, %s, %s)",
                    batch,
                )
                batch = []
        current += timedelta(days=1)

    if batch:
        cur.executemany(
            "INSERT INTO analytics.orders (customer_id, region_id, amount, order_date) VALUES (%s, %s, %s, %s)",
            batch,
        )

    cur.execute("SELECT order_id FROM analytics.orders")
    order_ids = [r[0] for r in cur.fetchall()]
    return order_ids


def seed_refunds(cur, order_ids: list[int], region_ids: dict[str, int]) -> None:
    north_id = region_ids[ANOMALY_REGION]
    current = date(2024, 1, 1)
    batch = []

    while current <= date(2025, 12, 31):
        month_start = current.replace(day=1)
        if month_start.year == ANOMALY_MONTH.year and month_start.month == ANOMALY_MONTH.month:
            for _ in range(ANOMALY_REFUND_COUNT):
                oid = random.choice(order_ids)
                amount = round(random.uniform(300.0, 800.0), 2)
                day = random.randint(1, 28)
                batch.append((oid, north_id, amount, date(2025, 6, day), random.choice(REFUND_REASONS)))
            for region_name, rid in region_ids.items():
                if region_name == ANOMALY_REGION:
                    continue
                for _ in range(random.randint(15, 30)):
                    oid = random.choice(order_ids)
                    amount = round(random.uniform(25.0, 200.0), 2)
                    batch.append((oid, rid, amount, date(2025, 6, random.randint(1, 28)), random.choice(REFUND_REASONS)))
            current = date(2025, 7, 1)
            if batch:
                cur.executemany(
                    "INSERT INTO analytics.refunds (order_id, region_id, amount, refund_date, reason) VALUES (%s, %s, %s, %s, %s)",
                    batch,
                )
                batch = []
            continue

        monthly_refunds = random.randint(80, 120)
        for _ in range(monthly_refunds):
            oid = random.choice(order_ids)
            rid = region_ids[random.choice(REGIONS)]
            amount = round(random.uniform(25.0, 200.0), 2)
            day = random.randint(1, 28)
            try:
                refund_date = current.replace(day=day)
            except ValueError:
                refund_date = current.replace(day=28)
            batch.append((oid, rid, amount, refund_date, random.choice(REFUND_REASONS)))

        if len(batch) >= 1000:
            cur.executemany(
                "INSERT INTO analytics.refunds (order_id, region_id, amount, refund_date, reason) VALUES (%s, %s, %s, %s, %s)",
                batch,
            )
            batch = []

        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    if batch:
        cur.executemany(
            "INSERT INTO analytics.refunds (order_id, region_id, amount, refund_date, reason) VALUES (%s, %s, %s, %s, %s)",
            batch,
        )


def seed_support_tickets(cur, customer_ids: list[int], count: int = 3000) -> None:
    subjects = ["Billing question", "Product not working", "Shipping delay", "Refund request", "Account access issue"]
    batch = []
    for i in range(count):
        cid = random.choice(customer_ids)
        batch.append((cid, random.choice(subjects), f"Support ticket body #{i}", random.choice(["open", "closed", "pending"])))
        if len(batch) >= 500:
            cur.executemany(
                "INSERT INTO analytics.support_tickets (customer_id, subject, body, status) VALUES (%s, %s, %s, %s)",
                batch,
            )
            batch = []
    if batch:
        cur.executemany(
            "INSERT INTO analytics.support_tickets (customer_id, subject, body, status) VALUES (%s, %s, %s, %s)",
            batch,
        )


def clear_analytics(cur) -> None:
    cur.execute(
        "TRUNCATE analytics.support_tickets, analytics.refunds, analytics.orders, analytics.customers, analytics.regions RESTART IDENTITY CASCADE"
    )


def main() -> None:
    print("Seeding InsightOps analytics database...")
    print(f"Planted anomaly: {ANOMALY_REFUND_COUNT} refunds in {ANOMALY_REGION} region, June 2025")

    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            clear_analytics(cur)
            region_ids = seed_regions(cur)
            print(f"  Regions: {len(region_ids)}")

            customer_ids = seed_customers(cur, region_ids)
            print(f"  Customers: {len(customer_ids)}")

            order_ids = seed_orders(cur, customer_ids, region_ids)
            print(f"  Orders: {len(order_ids)}")

            seed_refunds(cur, order_ids, region_ids)
            cur.execute("SELECT COUNT(*) AS cnt FROM analytics.refunds")
            print(f"  Refunds: {cur.fetchone()['cnt']}")

            seed_support_tickets(cur, customer_ids)
            cur.execute("SELECT COUNT(*) AS cnt FROM analytics.support_tickets")
            print(f"  Support tickets: {cur.fetchone()['cnt']}")

            cur.execute(
                """
                SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
                FROM analytics.refunds r
                JOIN analytics.regions reg ON r.region_id = reg.region_id
                WHERE reg.name = %s
                  AND DATE_TRUNC('month', r.refund_date) = %s
                """,
                (ANOMALY_REGION, ANOMALY_MONTH),
            )
            row = cur.fetchone()
            print(f"  Anomaly verification: {row['cnt']} refunds, ${float(row['total']):,.2f} in {ANOMALY_REGION} June 2025")
        conn.commit()
    print("Seed complete.")


if __name__ == "__main__":
    main()
