import requests
import pandas as pd
import json


def fetch_enriched_municipalities():
    url = "https://query.wikidata.org/sparql"
    headers = {
        'User-Agent': 'MunicipalCrawlerBot/7.0 (dein-email@beispiel.de)',
        'Accept': 'application/sparql-results+json'
    }

    query = """
    SELECT DISTINCT ?itemLabel ?website ?ags ?typeLabel ?plz ?landkreisLabel ?bundeslandLabel WHERE {
      ?item wdt:P439 ?ags. 
      ?item wdt:P856 ?website.

      OPTIONAL { ?item wdt:P31 ?type. }
      OPTIONAL { ?item wdt:P281 ?plz. }
      OPTIONAL { ?item wdt:P131 ?landkreis. }

      # Begrenzung auf Deutschland, um die Suche für den Server einzugrenzen
      ?item wdt:P17 wd:Q183. 

      OPTIONAL { 
        ?item wdt:P131* ?bundesland.
        ?bundesland wdt:P31 wd:Q1221156. 
      }

      SERVICE wikibase:label { bd:serviceParam wikibase:language "de". }
    }
    """

    print("Starte Abfrage...")

    try:
        # POST ist bei großen Datenmengen stabiler als GET
        response = requests.post(url, data={'query': query}, headers=headers, timeout=300)

        if response.status_code == 200:
            # HIER: strict=False verhindert den "Invalid control character" Fehler
            data = json.loads(response.text, strict=False)

            results = []
            for entry in data['results']['bindings']:
                results.append({
                    'Organisation': entry.get('itemLabel', {}).get('value', ''),
                    'Internetadresse': entry.get('website', {}).get('value', ''),
                    'AGS': entry.get('ags', {}).get('value', ''),
                    'Typ': entry.get('typeLabel', {}).get('value', ''),
                    'PLZ': entry.get('plz', {}).get('value', ''),
                    'Landkreis': entry.get('landkreisLabel', {}).get('value', ''),
                    'Bundesland': entry.get('bundeslandLabel', {}).get('value', '')
                })

            df = pd.DataFrame(results)
            if not df.empty:
                df['Internetadresse'] = df['Internetadresse'].str.lower().str.strip().str.rstrip('/')
                df.to_csv('municipalities_enriched.csv', index=False, sep=';', encoding='utf-8-sig')
                print(f"Erfolg! {len(df)} Zeilen gespeichert.")
            return df
        else:
            print(f"HTTP Fehler: {response.status_code}")
    except Exception as e:
        print(f"Fehler beim Verarbeiten: {e}")


if __name__ == "__main__":
    fetch_enriched_municipalities()