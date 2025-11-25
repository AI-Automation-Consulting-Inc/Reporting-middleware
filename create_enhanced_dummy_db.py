#!/usr/bin/env python3
"""
Enhanced reporting warehouse generator.

This script creates an analytic SQLite database called ``enhanced_sales.db`` with
multiple dimensions and a combined sales/pipeline fact table that can answer
complex questions about revenue, renewals, expansions, returns, and pipeline
stages. The row count defaults to 1,000 but can be overridden via the
FACT_ROW_COUNT environment variable.
"""
from __future__ import annotations

import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_NAME = os.getenv("DUMMY_DB_NAME", "enhanced_sales.db")
FACT_ROW_COUNT = int(os.getenv("FACT_ROW_COUNT", "1000"))
DATA_SEED = int(os.getenv("DATA_SEED", "42"))

random.seed(DATA_SEED)

TODAY = date.today()
START_DATE = TODAY - timedelta(days=3 * 365)


def random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 1)))


def create_schema(conn: sqlite3.Connection) -> None:
    schema_sql = """
    PRAGMA foreign_keys = OFF;

    DROP VIEW IF EXISTS sales_enriched;
    DROP TABLE IF EXISTS fact_sales_pipeline;
    DROP TABLE IF EXISTS dim_date;
    DROP TABLE IF EXISTS dim_customer;
    DROP TABLE IF EXISTS dim_region;
    DROP TABLE IF EXISTS dim_product;
    DROP TABLE IF EXISTS dim_sales_rep;
    DROP TABLE IF EXISTS dim_channel;
    DROP TABLE IF EXISTS dim_pipeline_stage;
    DROP TABLE IF EXISTS dim_account_hierarchy;

    CREATE TABLE dim_region (
        region_id INTEGER PRIMARY KEY,
        country TEXT NOT NULL,
        state_province TEXT NOT NULL,
        geo_cluster TEXT NOT NULL,
        currency_default TEXT NOT NULL,
        sales_area TEXT NOT NULL
    );

    CREATE TABLE dim_channel (
        channel_id INTEGER PRIMARY KEY,
        channel_name TEXT NOT NULL,
        channel_type TEXT NOT NULL,
        is_digital INTEGER NOT NULL
    );

    CREATE TABLE dim_pipeline_stage (
        stage_id INTEGER PRIMARY KEY,
        stage_name TEXT NOT NULL,
        stage_order INTEGER NOT NULL,
        stage_category TEXT NOT NULL
    );

    CREATE TABLE dim_account_hierarchy (
        parent_account_id INTEGER PRIMARY KEY,
        parent_account_name TEXT NOT NULL,
        segment TEXT NOT NULL,
        global_region TEXT NOT NULL
    );

    CREATE TABLE dim_customer (
        customer_id INTEGER PRIMARY KEY,
        customer_name TEXT NOT NULL,
        industry TEXT NOT NULL,
        customer_tier TEXT NOT NULL,
        lifecycle_stage TEXT NOT NULL,
        parent_customer_id INTEGER,
        hq_region_id INTEGER NOT NULL,
        size_bucket TEXT NOT NULL,
        is_enterprise INTEGER NOT NULL,
        FOREIGN KEY (parent_customer_id) REFERENCES dim_account_hierarchy(parent_account_id),
        FOREIGN KEY (hq_region_id) REFERENCES dim_region(region_id)
    );

    CREATE TABLE dim_product (
        product_id INTEGER PRIMARY KEY,
        product_name TEXT NOT NULL,
        category TEXT NOT NULL,
        segment TEXT NOT NULL,
        launch_date TEXT NOT NULL,
        lifecycle_status TEXT NOT NULL,
        sku TEXT NOT NULL,
        is_subscription INTEGER NOT NULL
    );

    CREATE TABLE dim_sales_rep (
        sales_rep_id INTEGER PRIMARY KEY,
        rep_name TEXT NOT NULL,
        team TEXT NOT NULL,
        manager TEXT NOT NULL,
        quota REAL NOT NULL,
        territory_region_id INTEGER NOT NULL,
        channel_specialty TEXT NOT NULL,
        FOREIGN KEY (territory_region_id) REFERENCES dim_region(region_id)
    );

    CREATE TABLE dim_date (
        date_key TEXT PRIMARY KEY,
        calendar_date TEXT NOT NULL,
        year INTEGER NOT NULL,
        month INTEGER NOT NULL,
        month_name TEXT NOT NULL,
        quarter TEXT NOT NULL,
        week INTEGER NOT NULL,
        day_of_week TEXT NOT NULL,
        fiscal_year INTEGER NOT NULL,
        fiscal_quarter TEXT NOT NULL,
        is_fiscal_year_start INTEGER NOT NULL
    );

    CREATE TABLE fact_sales_pipeline (
        fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
        deal_id TEXT NOT NULL UNIQUE,
        customer_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        region_id INTEGER NOT NULL,
        sales_rep_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        stage_id INTEGER NOT NULL,
        parent_account_id INTEGER,
        contract_type TEXT NOT NULL,
        deal_status TEXT NOT NULL,
        pipeline_stage TEXT NOT NULL,
        order_date TEXT NOT NULL,
        sale_date TEXT NOT NULL,
        ship_date TEXT,
        created_date TEXT NOT NULL,
        stage_updated_date TEXT NOT NULL,
        renewal_date TEXT,
        currency TEXT NOT NULL,
        lead_source TEXT NOT NULL,
        unit_price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        list_price REAL NOT NULL,
        discount_rate REAL NOT NULL,
        net_revenue REAL NOT NULL,
        cost REAL NOT NULL,
        gross_margin REAL NOT NULL,
        arr REAL NOT NULL,
        acv REAL NOT NULL,
        probability REAL NOT NULL,
        pipeline_value REAL NOT NULL,
        renewal_flag INTEGER NOT NULL,
        expansion_flag INTEGER NOT NULL,
        return_flag INTEGER NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES dim_customer(customer_id),
        FOREIGN KEY (product_id) REFERENCES dim_product(product_id),
        FOREIGN KEY (region_id) REFERENCES dim_region(region_id),
        FOREIGN KEY (sales_rep_id) REFERENCES dim_sales_rep(sales_rep_id),
        FOREIGN KEY (channel_id) REFERENCES dim_channel(channel_id),
        FOREIGN KEY (stage_id) REFERENCES dim_pipeline_stage(stage_id),
        FOREIGN KEY (parent_account_id) REFERENCES dim_account_hierarchy(parent_account_id)
    );
    """
    conn.executescript(schema_sql)


def insert_rows(conn: sqlite3.Connection, table: str, columns: list[str], rows: list[tuple]) -> None:
    if not rows:
        return
    placeholders = ", ".join(["?"] * len(columns))
    column_clause = ", ".join(columns)
    conn.executemany(
        f"INSERT INTO {table} ({column_clause}) VALUES ({placeholders})",
        rows,
    )


def build_region_dimension() -> tuple[list[tuple], list[dict]]:
    templates = [
        ("United States", "California", "AMER", "USD", "Enterprise West"),
        ("United States", "New York", "AMER", "USD", "Strategic East"),
        ("Canada", "Ontario", "AMER", "CAD", "North Growth"),
        ("Germany", "Bavaria", "EMEA", "EUR", "DACH Manufacturing"),
        ("United Kingdom", "England", "EMEA", "GBP", "UK Public Sector"),
        ("India", "Karnataka", "APAC", "INR", "APAC Aerospace"),
        ("Singapore", "Singapore", "APAC", "SGD", "SEA Financial"),
        ("Australia", "New South Wales", "APAC", "AUD", "ANZ Commercial"),
    ]
    rows, meta = [], []
    for idx, tpl in enumerate(templates, start=1):
        row = (idx, *tpl)
        rows.append(row)
        meta.append(
            {
                "region_id": idx,
                "country": tpl[0],
                "state": tpl[1],
                "geo_cluster": tpl[2],
                "currency": tpl[3],
                "sales_area": tpl[4],
            }
        )
    return rows, meta


def build_channel_dimension() -> tuple[list[tuple], list[dict]]:
    templates = [
        ("Inbound Marketing", "Digital", 1),
        ("Outbound SDR", "Sales", 0),
        ("Partner Reseller", "Partner", 0),
        ("Field Events", "Events", 0),
        ("Customer Success", "Expansion", 0),
        ("E-Commerce", "Digital", 1),
    ]
    rows, meta = [], []
    for idx, tpl in enumerate(templates, start=1):
        row = (idx, *tpl)
        rows.append(row)
        meta.append(
            {
                "channel_id": idx,
                "channel_name": tpl[0],
                "channel_type": tpl[1],
                "is_digital": tpl[2],
            }
        )
    return rows, meta


def build_pipeline_stages() -> tuple[list[tuple], list[dict]]:
    templates = [
        ("Qualification", 1, "early", 0.25),
        ("Discovery", 2, "early", 0.35),
        ("Proposal", 3, "middle", 0.5),
        ("Evaluation", 4, "middle", 0.6),
        ("Negotiation", 5, "late", 0.75),
        ("Closed Won", 6, "late", 1.0),
        ("Closed Lost", 7, "late", 0.0),
    ]
    rows, meta = [], []
    for idx, tpl in enumerate(templates, start=1):
        row = (idx, tpl[0], tpl[1], tpl[2])
        rows.append(row)
        meta.append(
            {
                "stage_id": idx,
                "stage_name": tpl[0],
                "stage_order": tpl[1],
                "stage_category": tpl[2],
                "default_probability": tpl[3],
            }
        )
    return rows, meta


def build_parent_accounts() -> tuple[list[tuple], list[dict]]:
    templates = [
        ("Global Aerospace Group", "Enterprise", "AMER"),
        ("Helios Industrial Holdings", "Enterprise", "EMEA"),
        ("Pacific Medical Consortium", "Enterprise", "APAC"),
        ("Zenith Mobility Partners", "Strategic", "EMEA"),
        ("Aurora Defense Systems", "Strategic", "AMER"),
        ("Atlas Infrastructure Group", "Enterprise", "APAC"),
    ]
    rows, meta = [], []
    for idx, tpl in enumerate(templates, start=1):
        row = (idx, *tpl)
        rows.append(row)
        meta.append(
            {
                "parent_account_id": idx,
                "parent_account_name": tpl[0],
                "segment": tpl[1],
                "global_region": tpl[2],
            }
        )
    return rows, meta


def build_customers(
    parent_accounts: list[dict], regions: list[dict]
) -> tuple[list[tuple], list[dict]]:
    companies = [
        ("Hindustan Aeronautics", "Aerospace"),
        ("Orion Biotech", "Healthcare"),
        ("Nimbus Cloud Logistics", "Logistics"),
        ("Quantum Retail Group", "Retail"),
        ("Stellar Defense Labs", "Defense"),
        ("Atlas Manufacturing", "Manufacturing"),
        ("Helix Pharmaceuticals", "Healthcare"),
        ("BluePeak Oilfield", "Energy"),
        ("Aurora Airlines", "Aviation"),
        ("Crest Financial", "Financial Services"),
        ("Vector Mobility", "Automotive"),
        ("Summit Renewable Power", "Energy"),
        ("Polar Minerals", "Mining"),
        ("Evergreen Foods", "CPG"),
        ("Nova Robotics", "Technology"),
        ("OrbitSat Communications", "Telecom"),
        ("Zenith Marine Works", "Marine"),
        ("Metro Healthcare Network", "Healthcare"),
        ("Ionis Semiconductor", "Technology"),
        ("Equinox Space Systems", "Aerospace"),
        ("Helion Cybersecurity", "Technology"),
        ("Mirage Entertainment", "Media"),
        ("Vanguard Insurance", "Insurance"),
        ("GlobeRail Transit", "Transportation"),
        ("Terranova Agritech", "Agriculture"),
    ]
    tiers = ["Enterprise", "Mid-Market", "Growth"]
    lifecycle = ["Prospect", "Active", "Expansion", "Churn Risk"]
    size_buckets = ["<100", "100-999", "1000-4999", "5000+"]
    rows, meta = [], []
    for idx, (name, industry) in enumerate(companies, start=1):
        tier = random.choices(tiers, weights=[0.4, 0.4, 0.2])[0]
        parent = random.choice(parent_accounts)["parent_account_id"]
        region = random.choice(regions)["region_id"]
        lifecycle_stage = random.choice(lifecycle)
        size_bucket = (
            "5000+" if tier == "Enterprise" else random.choice(size_buckets[:-1])
        )
        rows.append(
            (
                idx,
                name,
                industry,
                tier,
                lifecycle_stage,
                parent,
                region,
                size_bucket,
                1 if tier == "Enterprise" else 0,
            )
        )
        meta.append(
            {
                "customer_id": idx,
                "customer_name": name,
                "industry": industry,
                "tier": tier,
                "parent_account_id": parent,
                "region_id": region,
            }
        )
    return rows, meta


def build_products() -> tuple[list[tuple], list[dict]]:
    templates = [
        ("AeroNav Suite", "Navigation", "Avionics", date(2022, 5, 1), "Active", "AN-100", 1, 25000),
        ("Helios Predictive Maintenance", "Analytics", "Industrial IoT", date(2021, 2, 15), "Active", "PM-820", 1, 18000),
        ("Quantum Shield", "Security", "Cyber", date(2020, 11, 30), "Active", "QS-640", 1, 32000),
        ("Nova Manufacturing Execution", "Operations", "Manufacturing", date(2019, 7, 12), "Mature", "ME-410", 1, 22000),
        ("Stratos ERP", "Finance", "Enterprise", date(2018, 3, 8), "Mature", "ERP-300", 0, 45000),
        ("Vector Drone Guidance", "Navigation", "Defense", date(2023, 4, 20), "Growth", "DG-150", 0, 38000),
        ("Helix CRM", "Sales", "Horizontal SaaS", date(2022, 1, 14), "Active", "CRM-510", 1, 16000),
        ("Summit Analytics", "Analytics", "Energy", date(2021, 9, 5), "Active", "AN-920", 1, 28000),
        ("PulseCare Platform", "Healthcare", "Healthcare", date(2019, 12, 2), "Mature", "HC-210", 1, 30000),
        ("OrbitSat IoT Hub", "Connectivity", "Telecom", date(2020, 6, 18), "Active", "IOT-110", 1, 14000),
        ("TerraLog Logistics", "Logistics", "Transportation", date(2023, 1, 10), "Growth", "LG-360", 0, 26000),
        ("Zenith Retail Cloud", "Commerce", "Retail", date(2022, 8, 9), "Active", "RC-780", 1, 21000),
    ]
    rows, meta = [], []
    for idx, tpl in enumerate(templates, start=1):
        product_name, category, segment, launch_date, lifecycle_status, sku, is_sub, base_price = tpl
        rows.append(
            (
                idx,
                product_name,
                category,
                segment,
                launch_date.isoformat(),
                lifecycle_status,
                sku,
                is_sub,
            )
        )
        meta.append(
            {
                "product_id": idx,
                "product_name": product_name,
                "category": category,
                "segment": segment,
                "is_subscription": bool(is_sub),
                "base_price": base_price,
            }
        )
    return rows, meta


def build_sales_reps(region_meta: list[dict]) -> tuple[list[tuple], list[dict]]:
    rep_names = [
        "Riya Kapoor",
        "Ethan Walsh",
        "Carlos Martinez",
        "Priya Menon",
        "Amelia Clarke",
        "Noah Fischer",
        "Sofia Rossi",
        "Marcus Liu",
        "Helena Gomez",
        "Jacob Stein",
    ]
    teams = ["Enterprise", "Strategic", "Growth", "Renewals"]
    managers = ["Alex Morgan", "Jordan Patel", "Casey Liu"]
    specialties = ["Enterprise", "Partner", "Digital", "Renewal"]
    rows, meta = [], []
    for idx, name in enumerate(rep_names, start=1):
        territory = random.choice(region_meta)
        row = (
            idx,
            name,
            random.choice(teams),
            random.choice(managers),
            random.randint(900000, 5000000),
            territory["region_id"],
            random.choice(specialties),
        )
        rows.append(row)
        meta.append(
            {
                "sales_rep_id": idx,
                "rep_name": name,
                "territory_region_id": territory["region_id"],
            }
        )
    return rows, meta


def generate_date_dimension(start: date, end: date) -> list[tuple]:
    rows = []
    current = start
    while current <= end:
        date_key = current.strftime("%Y%m%d")
        month_name = current.strftime("%B")
        quarter = f"Q{((current.month - 1) // 3) + 1}"

        fiscal_year = current.year if current.month >= 2 else current.year - 1
        fiscal_month = ((current.month - 2) % 12) + 1
        fiscal_quarter = f"FQ{((fiscal_month - 1) // 3) + 1}"
        is_fy_start = 1 if fiscal_month == 1 else 0

        rows.append(
            (
                date_key,
                current.isoformat(),
                current.year,
                current.month,
                month_name,
                quarter,
                int(current.strftime("%V")),
                current.strftime("%A"),
                fiscal_year,
                fiscal_quarter,
                is_fy_start,
            )
        )
        current += timedelta(days=1)
    return rows


def build_fact_rows(
    row_count: int,
    customers: list[dict],
    products: list[dict],
    regions: list[dict],
    reps: list[dict],
    channels: list[dict],
    stages: list[dict],
) -> list[tuple]:
    lead_sources = [
        "Website",
        "Outbound Call",
        "Trade Show",
        "Partner Referral",
        "Customer Upsell",
        "Webinar",
    ]
    contract_types = ["new", "renewal", "expansion"]
    rows = []
    for idx in range(1, row_count + 1):
        customer = random.choice(customers)
        product = random.choice(products)
        region = next(r for r in regions if r["region_id"] == customer["region_id"])
        rep = random.choice(reps)
        channel = random.choice(channels)
        stage = random.choice(stages)

        contract_type = random.choices(contract_types, weights=[0.6, 0.2, 0.2])[0]
        discount_floor = 0.05 if customer["tier"] == "Enterprise" else 0.02
        discount_rate = round(random.uniform(discount_floor, 0.3), 4)
        list_price = product["base_price"]
        quantity = random.randint(1, 200 if customer["tier"] == "Enterprise" else 80)
        unit_price = round(list_price * (1 - discount_rate), 2)
        net_revenue = round(unit_price * quantity, 2)
        cost = round(net_revenue * random.uniform(0.45, 0.7), 2)
        gross_margin = round(net_revenue - cost, 2)

        order_date = random_date(START_DATE, TODAY)
        created_date = (order_date - timedelta(days=random.randint(5, 90))).isoformat()
        stage_updated_date = (
            order_date - timedelta(days=random.randint(0, 20))
        ).isoformat()
        ship_date = None
        renewal_date = None
        sale_date = order_date.isoformat()

        deal_status = "open"
        return_flag = 0

        if stage["stage_name"] == "Closed Won":
            deal_status = "closed_won"
            ship_date = (order_date + timedelta(days=random.randint(1, 30))).isoformat()
        elif stage["stage_name"] == "Closed Lost":
            deal_status = "closed_lost"

        if deal_status == "closed_won" and random.random() < 0.05:
            deal_status = "returned"
            return_flag = 1
            net_revenue = -abs(net_revenue)
            gross_margin = net_revenue - abs(cost)

        renewal_flag = 1 if contract_type == "renewal" else 0
        expansion_flag = 1 if contract_type == "expansion" else 0

        if product["is_subscription"]:
            renewal_date = (order_date + timedelta(days=365)).isoformat()
            arr = net_revenue
        else:
            arr = 0.0

        acv = arr if arr else max(net_revenue, 0.0)

        probability = stage["default_probability"]
        if deal_status == "closed_won":
            probability = 1.0
        elif deal_status in {"closed_lost", "returned"}:
            probability = 0.0

        if deal_status in {"closed_lost", "returned"}:
            pipeline_value = 0.0
        elif deal_status == "closed_won":
            pipeline_value = net_revenue
        else:
            pipeline_value = round(net_revenue * probability, 2)

        rows.append(
            (
                f"DL-{idx:05d}",
                customer["customer_id"],
                product["product_id"],
                region["region_id"],
                rep["sales_rep_id"],
                channel["channel_id"],
                stage["stage_id"],
                customer["parent_account_id"],
                contract_type,
                deal_status,
                stage["stage_name"],
                order_date.isoformat(),
                sale_date,
                ship_date,
                created_date,
                stage_updated_date,
                renewal_date,
                region["currency"],
                random.choice(lead_sources),
                unit_price,
                quantity,
                list_price,
                discount_rate,
                net_revenue,
                cost,
                gross_margin,
                arr,
                acv,
                probability,
                pipeline_value,
                renewal_flag,
                expansion_flag,
                return_flag,
            )
        )
    return rows


def create_enriched_view(conn: sqlite3.Connection) -> None:
    view_sql = """
    CREATE VIEW IF NOT EXISTS sales_enriched AS
    SELECT
        f.*,
        c.customer_name,
        c.industry,
        c.customer_tier,
        p.product_name,
        p.category AS product_category,
        r.country,
        r.geo_cluster,
        sr.rep_name,
        ch.channel_name,
        ps.stage_category
    FROM fact_sales_pipeline f
    JOIN dim_customer c ON c.customer_id = f.customer_id
    JOIN dim_product p ON p.product_id = f.product_id
    JOIN dim_region r ON r.region_id = f.region_id
    JOIN dim_sales_rep sr ON sr.sales_rep_id = f.sales_rep_id
    JOIN dim_channel ch ON ch.channel_id = f.channel_id
    JOIN dim_pipeline_stage ps ON ps.stage_id = f.stage_id;
    """
    conn.executescript(view_sql)


def main() -> None:
    db_path = Path(DB_NAME)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        create_schema(conn)

        region_rows, region_meta = build_region_dimension()
        channel_rows, channel_meta = build_channel_dimension()
        stage_rows, stage_meta = build_pipeline_stages()
        account_rows, account_meta = build_parent_accounts()
        product_rows, product_meta = build_products()
        customer_rows, customer_meta = build_customers(account_meta, region_meta)
        rep_rows, rep_meta = build_sales_reps(region_meta)
        date_rows = generate_date_dimension(START_DATE, TODAY)

        insert_rows(conn, "dim_region", ["region_id", "country", "state_province", "geo_cluster", "currency_default", "sales_area"], region_rows)
        insert_rows(conn, "dim_channel", ["channel_id", "channel_name", "channel_type", "is_digital"], channel_rows)
        insert_rows(conn, "dim_pipeline_stage", ["stage_id", "stage_name", "stage_order", "stage_category"], stage_rows)
        insert_rows(conn, "dim_account_hierarchy", ["parent_account_id", "parent_account_name", "segment", "global_region"], account_rows)
        insert_rows(conn, "dim_product", ["product_id", "product_name", "category", "segment", "launch_date", "lifecycle_status", "sku", "is_subscription"], product_rows)
        insert_rows(conn, "dim_customer", ["customer_id", "customer_name", "industry", "customer_tier", "lifecycle_stage", "parent_customer_id", "hq_region_id", "size_bucket", "is_enterprise"], customer_rows)
        insert_rows(conn, "dim_sales_rep", ["sales_rep_id", "rep_name", "team", "manager", "quota", "territory_region_id", "channel_specialty"], rep_rows)
        insert_rows(conn, "dim_date", ["date_key", "calendar_date", "year", "month", "month_name", "quarter", "week", "day_of_week", "fiscal_year", "fiscal_quarter", "is_fiscal_year_start"], date_rows)

        fact_rows = build_fact_rows(
            FACT_ROW_COUNT,
            customer_meta,
            product_meta,
            region_meta,
            rep_meta,
            channel_meta,
            stage_meta,
        )
        insert_rows(
            conn,
            "fact_sales_pipeline",
            [
                "deal_id",
                "customer_id",
                "product_id",
                "region_id",
                "sales_rep_id",
                "channel_id",
                "stage_id",
                "parent_account_id",
                "contract_type",
                "deal_status",
                "pipeline_stage",
                "order_date",
                "sale_date",
                "ship_date",
                "created_date",
                "stage_updated_date",
                "renewal_date",
                "currency",
                "lead_source",
                "unit_price",
                "quantity",
                "list_price",
                "discount_rate",
                "net_revenue",
                "cost",
                "gross_margin",
                "arr",
                "acv",
                "probability",
                "pipeline_value",
                "renewal_flag",
                "expansion_flag",
                "return_flag",
            ],
            fact_rows,
        )

        create_enriched_view(conn)
        conn.commit()
    finally:
        conn.close()

    print(
        f"Created {DB_NAME} with {len(date_rows)} dim_date rows and {len(fact_rows)} fact rows."
    )


if __name__ == "__main__":
    main()
