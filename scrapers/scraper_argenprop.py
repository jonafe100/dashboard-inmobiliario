from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime
import re

SEARCH_URL = "https://www.argenprop.com/departamentos/alquiler/capital-federal/2-dormitorios"

# SELECTORES APROXIMADOS – AJUSTAR CON DEVTOOLS SI HACE FALTA
CARD_SELECTOR = "div.listing__item"                 # TODO: revisar en DevTools
TITLE_SELECTOR = "a.card__title, h2.card__title"    # TODO
PRICE_SELECTOR = "div.card__price, span.card__price"  # TODO
LOCATION_SELECTOR = "div.card-location, p.card-location"  # TODO
DETAILS_SELECTOR = "div.card__info"                 # texto con m2/ambientes, etc.
NEXT_BUTTON_SELECTOR = "a[rel='next'], a[title='Siguiente']"

MAX_PRECIO_ARS = 750_000
USD_TO_ARS = 1500
fecha_extraccion = datetime.now().strftime("%Y-%m-%d")

# ===== helpers (mismas que antes) =====

def limpiar_precio(texto):
    if not texto:
        return None
    n = re.sub(r"[^\d]", "", texto)
    try:
        return int(n)
    except:
        return None

def detectar_moneda(precio_raw):
    if not precio_raw:
        return None
    t = precio_raw.upper()
    if "USD" in t or "U$S" in t:
        return "USD"
    if "$" in t or "ARS" in t:
        return "ARS"
    return None

def extraer_m2_desde_texto(texto):
    if not texto:
        return None
    m = re.search(r"(\d+)\s*(m²|m2)", texto.lower())
    return int(m.group(1)) if m else None

def extraer_ambientes_desde_texto(texto):
    if not texto:
        return None
    m = re.search(r"(\d+)\s*amb", texto.lower())
    return int(m.group(1)) if m else None

def scrape_page(page):
    cards = page.query_selector_all(CARD_SELECTOR)
    print(f"  → Avisos encontrados: {len(cards)}")
    data = []

    for card in cards:
        full_text = card.inner_text()

        title_el = card.query_selector(TITLE_SELECTOR)
        price_el = card.query_selector(PRICE_SELECTOR)
        loc_el = card.query_selector(LOCATION_SELECTOR)
        details_el = card.query_selector(DETAILS_SELECTOR)
        link_el = card.query_selector("a")

        titulo = title_el.inner_text().strip() if title_el else None
        precio_raw = price_el.inner_text().strip() if price_el else None
        ubicacion = loc_el.inner_text().strip() if loc_el else None
        detalles = details_el.inner_text().strip() if details_el else ""
        link = link_el.get_attribute("href") if link_el else None

        if link and link.startswith("/"):
            link = "https://www.argenprop.com" + link

        moneda = detectar_moneda(precio_raw)
        precio_num = limpiar_precio(precio_raw)
        precio_ars = None

        if precio_num:
            if moneda == "USD":
                precio_ars = precio_num * USD_TO_ARS
            elif moneda == "ARS":
                precio_ars = precio_num

        if precio_ars is not None and precio_ars > MAX_PRECIO_ARS:
            continue

        m2 = extraer_m2_desde_texto(full_text)
        ambientes = extraer_ambientes_desde_texto(full_text)

        precio_m2 = None
        if precio_ars and m2:
            precio_m2 = precio_ars / m2

        data.append({
            "portal": "argenprop",
            "fecha": fecha_extraccion,
            "titulo": titulo,
            "ubicacion": ubicacion,
            "precio_raw": precio_raw,
            "moneda": moneda,
            "precio_num": precio_num,
            "precio_ars": precio_ars,
            "m2": m2,
            "ambientes": ambientes,
            "precio_m2": precio_m2,
            "url": link,
            "texto_card": full_text
        })

    return data

def main():
    all_data = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print(f"\nAbriendo búsqueda Argenprop:\n{SEARCH_URL}\n")
        page.goto(SEARCH_URL)
        page.wait_for_timeout(5000)

        current = 1
        max_pages = 3

        while True:
            print(f"\nScrapeando página {current}...")
            all_data.extend(scrape_page(page))

            if current >= max_pages:
                break

            next_btn = page.query_selector(NEXT_BUTTON_SELECTOR)
            if not next_btn:
                print("→ No hay botón de siguiente, fin.")
                break

            next_btn.click()
            page.wait_for_timeout(5000)
            current += 1

        browser.close()

    df = pd.DataFrame(all_data)
    df.to_csv("argenprop_filtrado.csv", index=False, encoding="utf-8-sig")
    print(f"\n✔ Argenprop: guardé {len(all_data)} propiedades en argenprop_filtrado.csv")

if __name__ == "__main__":
    main()
