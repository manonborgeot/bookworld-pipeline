"""Pipeline BookWorld : extraction, transformation et chargement des ventes par pays."""

import sqlite3
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os

# --- Paramètres ---
SALES_CSV = "data/sales_raw.csv"
REFERENCE_DB = "data/bookworld_reference.db"
FINAL_DB = "bookworld_final.db"
SCHEMA_SQL = "schema_final.sql"
CATALOGUE_URL = "https://books.toscrape.com/"
EXCHANGE_URL = "https://api.frankfurter.dev/v2/rate/gbp/eur"
SALES_COLUMNS = ["order_id","order_date","book_id","country_code","channel_code","quantity","discount_rate","book_name"]          # colonnes à lire dans le CSV (sans les noms clients)
CORRECTIONS = {"NL": "Netherlands"}


# --- 1. Extraction ---
def extract_sales(path):
    """Lit le CSV des ventes, sans les colonnes nominatives."""
    sales = pd.read_csv(path, usecols=SALES_COLUMNS)
    return sales
    
def extract_reference(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Base de référence introuvable : {path}")

    """Lit les tables de référence utiles (pays et canaux) depuis la base SQLite."""
    conn = sqlite3.connect(path)

    query_countries = """
        SELECT country_code, country_name, currency_code
        FROM countries
    """
    countries = pd.read_sql(query_countries, conn)

    query_channels = """
        SELECT channel_code, channel_name, acquisition_cost_gbp, channel_group, is_active
        FROM channels
        WHERE is_active = 1
    """
    channels = pd.read_sql(query_channels, conn)

    conn.close()
    return countries, channels
    

def extract_catalogue(url):
    """Scrape la première page du catalogue : titre et prix en £."""
    page = requests.get(url, timeout=10)
    page.raise_for_status()

    soup = BeautifulSoup(page.content, "html.parser")

    livres = soup.find_all("article", class_="product_pod")
    if len(livres) == 0:
        raise ValueError("Aucun livre trouvé : la structure du site a peut-être changé.")
    liste =[]
    for livre in livres : 
        titre = livre.find("h3").find("a")["title"]
        prix = livre.find("p", class_="price_color").get_text(strip=True)
        liste.append({"book_name": titre, "price_gbp": prix})

    catalogue = pd.DataFrame(liste)
    catalogue["price_gbp"] = catalogue["price_gbp"].str.replace("£", "", regex=False).astype(float)
    return catalogue


def extract_exchange_rate(url):
    """Récupère le taux GBP → EUR du jour."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    recuperation = response.json()

    taux = recuperation["rate"]
    rate_date = recuperation["date"]
    base_currency = recuperation["base"]
    quote_currency = recuperation["quote"]

    return pd.DataFrame([{
        "rate_date": rate_date,
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "rate": taux
}])


# --- 2. Transformation ---
def transform(sales, countries, channels, catalogue, rate):
    """Nettoie, joint, calcule le CA et prépare les 6 tables finales."""


# --- 3. Chargement ---
def load(tables, db_path, schema_path):
    """Crée la base finale à partir du schéma et charge les tables."""


# --- Point d'entrée ---
def main():
    sales = extract_sales(SALES_CSV)
    countries, channels = extract_reference(REFERENCE_DB)
    catalogue = extract_catalogue(CATALOGUE_URL)
    exchange_rate = extract_exchange_rate(EXCHANGE_URL)
    print(exchange_rate.shape)

if __name__ == "__main__":
    main()