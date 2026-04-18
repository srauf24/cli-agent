CREATE SCHEMA raw;
CREATE SCHEMA staging;
CREATE SCHEMA marts;

CREATE TABLE raw.customers (
    customer_id INTEGER,
    customer_name VARCHAR,
    email VARCHAR,
    country VARCHAR,
    signup_date DATE
);

CREATE TABLE raw.products (
    product_id INTEGER,
    product_name VARCHAR,
    category VARCHAR,
    list_price DOUBLE
);

CREATE TABLE raw.orders (
    order_id INTEGER,
    customer_id INTEGER,
    order_ts TIMESTAMP,
    order_total DOUBLE,
    currency VARCHAR
);

CREATE TABLE raw.transactions (
    transaction_id INTEGER,
    order_id INTEGER,
    product_id INTEGER,
    customer_id INTEGER,
    quantity INTEGER,
    unit_price DOUBLE,
    transaction_ts TIMESTAMP
);

CREATE TABLE main.users (
    user_id INTEGER,
    customer_id INTEGER,
    is_active BOOLEAN,
    created_at TIMESTAMP
);

CREATE TABLE main.orders (
    order_id INTEGER,
    customer_id INTEGER,
    order_date DATE,
    total_revenue DOUBLE,
    status VARCHAR
);

INSERT INTO raw.customers VALUES
    (1001, 'Ana Rivera', 'ana@example.com', 'IE', DATE '2023-05-11'),
    (1002, 'Noah Kim', 'noah@example.com', 'US', DATE '2023-11-03'),
    (1003, 'Maya Singh', 'maya@example.com', 'GB', DATE '2024-02-20');

INSERT INTO raw.products VALUES
    (501, 'Aero Hoodie', 'Apparel', 45.00),
    (502, 'Data Mug', 'Accessories', 18.50),
    (503, 'Infra Boots', 'Footwear', 88.25);

INSERT INTO raw.orders VALUES
    (9001, 1001, TIMESTAMP '2026-01-05 10:15:00', 112.50, 'USD'),
    (9002, 1002, TIMESTAMP '2026-02-12 16:05:00', 74.00, 'USD'),
    (9003, 1003, TIMESTAMP '2026-03-19 09:42:00', 129.25, 'EUR');

INSERT INTO raw.transactions VALUES
    (7001, 9001, 501, 1001, 2, 45.00, TIMESTAMP '2026-01-05 10:20:00'),
    (7002, 9001, 502, 1001, 1, 22.50, TIMESTAMP '2026-01-05 10:21:00'),
    (7003, 9002, 503, 1002, 1, 74.00, TIMESTAMP '2026-02-12 16:06:00'),
    (7004, 9003, 501, 1003, 1, 45.00, TIMESTAMP '2026-03-19 09:45:00'),
    (7005, 9003, 503, 1003, 1, 84.25, TIMESTAMP '2026-03-19 09:46:00');

INSERT INTO main.users VALUES
    (1, 1001, TRUE, TIMESTAMP '2023-05-11 00:00:00'),
    (2, 1002, TRUE, TIMESTAMP '2023-11-03 00:00:00'),
    (3, 1003, FALSE, TIMESTAMP '2024-02-20 00:00:00');

INSERT INTO main.orders VALUES
    (9001, 1001, DATE '2026-01-05', 112.50, 'shipped'),
    (9002, 1002, DATE '2026-02-12', 74.00, 'delivered'),
    (9003, 1003, DATE '2026-03-19', 129.25, 'processing');

CREATE TABLE marts.fct_orders (
    order_id INTEGER,
    customer_id INTEGER,
    order_date DATE,
    total_revenue DOUBLE,
    product_id INTEGER,
    order_item_count INTEGER
);

INSERT INTO marts.fct_orders VALUES
    (9001, 1001, DATE '2026-01-05', 112.50, 501, 2),
    (9001, 1001, DATE '2026-01-05', 42.00, 502, 1),
    (9002, 1002, DATE '2026-02-12', 74.00, 503, 1),
    (9003, 1003, DATE '2026-03-19', 129.25, 503, 2);

CREATE TABLE marts.dim_products (
    product_id INTEGER,
    product_name VARCHAR,
    category VARCHAR,
    is_active BOOLEAN
);

INSERT INTO marts.dim_products VALUES
    (501, 'Aero Hoodie', 'Apparel', TRUE),
    (502, 'Data Mug', 'Accessories', TRUE),
    (503, 'Infra Boots', 'Footwear', TRUE);

CREATE TABLE marts.dim_customers (
    customer_id INTEGER,
    customer_name VARCHAR,
    country VARCHAR,
    segment VARCHAR
);

INSERT INTO marts.dim_customers VALUES
    (1001, 'Ana Rivera', 'IE', 'new'),
    (1002, 'Noah Kim', 'US', 'returning'),
    (1003, 'Maya Singh', 'GB', 'new');

CREATE VIEW staging.stg_transactions AS
    SELECT *
    FROM raw.transactions;

CREATE VIEW staging.stg_order_lines AS
    SELECT
        transaction_id,
        order_id,
        product_id,
        customer_id,
        quantity,
        unit_price,
        transaction_ts
    FROM raw.transactions;
