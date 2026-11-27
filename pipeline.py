"""Pipeline BookWorld : extraction, transformation et chargement des ventes par pays."""

import sqlite3
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import sys

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
    """Lit les tables de référence utiles (pays et canaux) depuis la base SQLite."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Base de référence introuvable : {path}")
    
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


def extract_exchange_rates(url):
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
def transform(sales, countries, channels, catalogue, exchange_rates):
    """Nettoie, joint, calcule le CA et prépare les 6 tables finales."""

    # 1. Taux et date (depuis le DataFrame exchange_rate)
    taux = exchange_rates["rate"][0]
    rate_date = exchange_rates["rate_date"][0]

    # 2. Catalogue : price_eur
    catalogue = catalogue.copy()
    catalogue["price_eur"] = catalogue["price_gbp"] * taux

    # 3. Ventes : conversion de la date, contrôle d'unicité des order_id
    sales = sales.copy()
    sales["order_date"] = pd.to_datetime(sales["order_date"])
    doublons = sales.duplicated(subset=["order_id"]).sum()
    if doublons > 0:
        raise ValueError(f"{doublons} order_id en double : vérifier le fichier source")
    
    # 4. Jointure ventes ↔ catalogue (book_name) + contrôle : aucun prix manquant
    sales = sales.merge(catalogue, on="book_name", how="left")
    titres_sans_prix = sales.loc[sales["price_gbp"].isna(), "book_name"].unique()
    if len(titres_sans_prix) > 0:
        raise ValueError(f"Titres sans prix dans le catalogue : {list(titres_sans_prix)}")
    
    # 5. Jointure ventes ↔ pays + correction NL + contrôle : aucun pays sans nom
    countries = countries.copy()
    sales = sales.merge(countries[["country_code", "country_name"]], on="country_code", how="left")
    sales["country_name"] = sales["country_name"].fillna(sales["country_code"].map(CORRECTIONS))
    manquants = sales.loc[sales["country_name"].isna(), "country_code"].unique()
    if len(manquants) > 0:
        raise ValueError(f"Codes pays absents du référentiel : {list(manquants)}. Les ajouter dans CORRECTIONS.")
    ligne_nl = pd.DataFrame([{"country_code": "NL", "country_name": CORRECTIONS["NL"], "currency_code": "EUR"}])
    
    # 6. Calcul du CA brut et net
    sales["gross_revenue_gbp"] = sales['quantity'] * sales['price_gbp']
    sales["gross_revenue_eur"] = sales['quantity'] * sales['price_eur']
    sales["revenue_gbp"] = sales["gross_revenue_gbp"] * (1 - sales['discount_rate'])
    sales["revenue_eur"] = sales["gross_revenue_eur"] * (1 - sales['discount_rate'])

    # 7. Agrégation sales_by_country
    sales_by_country = (
        sales
        .groupby(['country_code','country_name'])
        .agg(
        total_orders=('order_id', 'nunique'),
        total_quantity=('quantity', 'sum'),
        total_revenue_gbp=('revenue_gbp','sum'),
        total_revenue_eur=('revenue_eur','sum'),
        total_gross_revenue_gbp=('gross_revenue_gbp','sum'),
        total_gross_revenue_eur=('gross_revenue_eur','sum'))
        .reset_index()
        .round(2)
        .sort_values(by='total_revenue_eur', ascending=False, ignore_index=True)
)
    # 8. Préparation des 6 tables finales (colonnes dans l'ordre du schéma)
    countries = pd.concat([countries, ligne_nl], ignore_index=True)
    countries_final = countries[["country_code", "country_name", "currency_code"]]

    channels_final = channels[["channel_code", "channel_name", "acquisition_cost_gbp", "channel_group", "is_active"]]

    # exchange_rate : déjà au format attendu, rien à faire 

    livres_ids = sales[["book_id", "book_name"]].drop_duplicates()
    catalogue_final = catalogue.merge(livres_ids, on="book_name", how='left')
    catalogue_final["rate_date"] = rate_date
    catalogue_final = catalogue_final[["book_id", "book_name", "price_gbp", "price_eur", "rate_date"]]

    sales_final = sales[["order_id", "order_date", "book_id", "country_code", "channel_code","quantity","discount_rate","revenue_gbp", "revenue_eur", "gross_revenue_gbp", "gross_revenue_eur"]].copy()
    sales_final["order_date"] = sales_final["order_date"].dt.strftime("%Y-%m-%d")

    sales_by_country_final = sales_by_country[["country_code", "country_name", "total_orders", "total_quantity",
                                           "total_revenue_gbp", "total_revenue_eur",
                                           "total_gross_revenue_gbp", "total_gross_revenue_eur"]]
    
    return {
        "countries": countries_final,
        "channels": channels_final,
        "exchange_rates": exchange_rates,
        "catalogue": catalogue_final,
        "sales": sales_final,
        "sales_by_country": sales_by_country_final,
    }


# --- 3. Chargement ---
def load(tables, db_path, schema_path):
    """Crée la base finale à partir du schéma et charge les tables."""
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"Fichier de schéma introuvable : {schema_path}")

    conn_final = sqlite3.connect(db_path)
    try:
        conn_final.execute("PRAGMA foreign_keys = ON")

        with open(schema_path, encoding="utf-8") as f:
            conn_final.executescript(f.read())

        for nom, df in tables.items():
            df.to_sql(nom, conn_final, if_exists="append", index=False)

        conn_final.commit()

    finally:
        conn_final.close()
    

# --- Point d'entrée ---
def main():
    etape = "démarrage"
    print("Démarrage du pipeline BookWorld")
    try:
        etape = "extraction des ventes"
        sales = extract_sales(SALES_CSV)
        print(f"  Ventes extraites : {len(sales)} lignes")

        etape = "extraction des référentiels"
        countries, channels = extract_reference(REFERENCE_DB)
        print(f"  Référentiels extraits : {len(countries)} pays, {len(channels)} canaux actifs")

        etape = "extraction du catalogue"
        catalogue = extract_catalogue(CATALOGUE_URL)
        print(f"  {len(catalogue)} livres récupérés en ligne")

        etape = "récupération du taux de change à date"
        exchange_rates = extract_exchange_rates(EXCHANGE_URL)
        print(f"  Le taux de change de GBP vers EUR était de {exchange_rates['rate'][0]} le {exchange_rates['rate_date'][0]}")

        etape = "transformation de l'ensemble des tables"
        tables = transform(sales, countries, channels, catalogue, exchange_rates)
        print("  Transformation terminée")

        etape = "chargement des tables"
        load(tables, FINAL_DB, SCHEMA_SQL)
        for nom, df in tables.items():
            print(f"  Table {nom} : {len(df)} lignes chargées")

    except Exception as erreur:
        print(f"ÉCHEC du pipeline pendant l'étape « {etape} » : {erreur}")
        sys.exit(1)

    print("Pipeline terminé : base finale créée.")
    
if __name__ == "__main__":
    main()