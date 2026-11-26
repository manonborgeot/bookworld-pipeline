-- 1. Suppression des tables (des plus dépendantes aux moins dépendantes)
DROP TABLE IF EXISTS sales_by_country;
DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS catalogue;
DROP TABLE IF EXISTS exchange_rates;
DROP TABLE IF EXISTS channels;
DROP TABLE IF EXISTS countries;

-- 2. Création des tables (dimensions d'abord, faits ensuite)

CREATE TABLE countries (
    country_code  TEXT PRIMARY KEY,
    country_name  TEXT NOT NULL,
    currency_code TEXT
);

CREATE TABLE channels (
    channel_code  TEXT PRIMARY KEY,
    channel_name  TEXT NOT NULL,
    acquisition_cost_gbp REAL,
    channel_group TEXT,
    is_active INTEGER
);

CREATE TABLE exchange_rates (
    rate_date  TEXT PRIMARY KEY, -- format ISO AAAA-MM-JJ
    base_currency  TEXT,
    quote_currency TEXT,
    rate REAL

);

CREATE TABLE catalogue (
    book_id  TEXT PRIMARY KEY,
    book_name  TEXT NOT NULL,
    price_gbp REAL,
    price_eur REAL,
    rate_date TEXT, -- format ISO AAAA-MM-JJ
    FOREIGN KEY (rate_date) REFERENCES exchange_rates(rate_date)
);

CREATE TABLE sales (
    order_id  TEXT PRIMARY KEY,
    order_date  TEXT NOT NULL, -- format ISO AAAA-MM-JJ
    book_id TEXT NOT NULL,
    country_code TEXT NOT NULL,
    channel_code TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    discount_rate REAL, 
    revenue_gbp REAL, 
    revenue_eur REAL, 
    gross_revenue_gbp REAL, 
    gross_revenue_eur REAL, 
    FOREIGN KEY (book_id) REFERENCES catalogue(book_id),
    FOREIGN KEY (country_code) REFERENCES countries(country_code), 
    FOREIGN KEY (channel_code) REFERENCES channels(channel_code)
    

);

CREATE TABLE sales_by_country (
    country_code  TEXT PRIMARY KEY,
    country_name  TEXT NOT NULL,
    total_orders INTEGER, 
    total_quantity INTEGER, 
    total_revenue_gbp REAL, 
    total_revenue_eur REAL, 
    total_gross_revenue_gbp REAL, 
    total_gross_revenue_eur REAL, 
    FOREIGN KEY (country_code) REFERENCES countries(country_code)
);