from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime
import re
import time

BASE_URL = "https://inmuebles.mercadolibre.com.ar/departamentos/alquiler/mas-de-4-dormitorios"
PAGES = list(range(1, 6))

USD_TO_ARS = 1500
MAX_PRECIO_ARS = 3_500_000

fecha = datetime.now().strftime("%Y-%m-%d")
OUTPUT_FILE = f"mercadolibre {datetime.now().strftime('%d.%m')}.csv"

def clean_text(text):
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip() if text else ""

def clean_price(text):
    if not text:
        return None
    n = re.sub(r"[^\d]", "", text)
    return int(n) if n.isdigit() else None

def moneda(text):
    t = text.upper() if text else ""
    return "USD" if "USD" in t or "U$S" in t else "ARS"

def extract_m2(text):
    m = re.search(r"(\d+)\s*m²", text, re.I)
    return int(m.group(1)) if m else None

def extract_ambientes(text):
    m = re.search(r"(\d+)\s*amb", text, re.I)
    return int(m.group(1)) if m else None

def contains_any(text, words):
    t = text.lower()
    return any(w in t for w in words)

def build_url(page):
    if page == 1:
        return BASE_URL
    offset = (page - 1) * 48 + 1
    return f"{BASE_URL}_Desde_{offset}_NoIndex_True"

def scrape_page(page, page_number):
    page.wait_for_timeout(5000)

    selectors = [
        "li.ui-search-layout__item",
        "div.ui-search-result__wrapper",
        "div.poly-card"
    ]

    cards = []
    for sel in selectors:
        cards = page.query_selector_all(sel)
        if cards:
            break

    print(f"Página {page_number}: {len(cards)} publicaciones")

    rows = []

    for card in cards:
        try:
            texto = clean_text(card.inner_text())

            link_el = card.query_selector("a[href]")
            url = link_el.get_attribute("href") if link_el else None

            img_el = card.query_selector("img")
            imagen = img_el.get_attribute("src") if img_el else None

            title_el = card.query_selector("h2") or card.query_selector("a")
            titulo = clean_text(title_el.inner_text()) if title_el else None

            price_text = texto
            mon = moneda(price_text)

            precio_num = clean_price(price_text)
            if not precio_num:
                continue

            precio_ars = precio_num * USD_TO_ARS if mon == "USD" else precio_num

            if precio_ars > MAX_PRECIO_ARS:
                continue

            m2 = extract_m2(texto)
            ambientes = extract_ambientes(texto)
            precio_m2 = int(round(precio_ars / m2)) if precio_ars and m2 else None

            rows.append({
                "portal": "mercadolibre",
                "fecha": fecha,
                "pagina": page_number,
                "barrio": None,
                "direccion": titulo,
                "precio_raw": f"{mon} {precio_num}" if mon == "USD" else f"$ {precio_num}",
                "moneda": mon,
                "expensas": None,
                "m2": m2,
                "ambientes": ambientes,
                "dormitorios": None,
                "banos": None,
                "precio_m2": precio_m2,
                "mascotas": contains_any(texto, ["mascotas", "pet friendly"]),
                "balcon": contains_any(texto, ["balcón", "balcon"]),
                "cochera": contains_any(texto, ["cochera", "garage", "coch."]),
                "terraza": contains_any(texto, ["terraza"]),
                "pileta": contains_any(texto, ["pileta", "piscina"]),
                "parrilla": contains_any(texto, ["parrilla"]),
                "luminoso": contains_any(texto, ["luminoso", "luminosa"]),
                "url": url,
                "imagen": imagen,
                "texto": texto
            })

        except Exception:
            continue

    return rows

def main():
    all_rows = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        for page_number in PAGES:
            url = build_url(page_number)
            print(f"\nCargando: {url}")

            page = browser.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                all_rows.extend(scrape_page(page, page_number))

            except Exception as e:
                print(f"Error en página {page_number}: {e}")

            finally:
                page.close()
                time.sleep(2)

        browser.close()

    df = pd.DataFrame(all_rows)

    df.to_csv(
        OUTPUT_FILE,
        sep=";",
        index=False,
        encoding="utf-8-sig"
    )

    print(f"\nArchivo generado: {OUTPUT_FILE}")
    print(f"Total propiedades: {len(df)}")

if __name__ == "__main__":
    main()