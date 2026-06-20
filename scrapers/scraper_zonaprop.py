from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime
import re
import time

# ================= CONFIG =================

BASE_URL = "https://www.zonaprop.com.ar/inmuebles-alquiler-villa-del-parque-villa-santa-rita-villa-general-mitre-flores-floresta-la-paternal-caballito-floresta-norte-floresta-floresta-sur-floresta-4-ambientes.html"
PAGES = [1, 2, 3, 4, 5, 6]

MAX_PRECIO_ARS = 2000000
USD_TO_ARS = 1500
MAX_RETRIES = 3

# Fecha archivo
fecha_formato = datetime.now().strftime("%d.%m")
OUTPUT_FILE = f"zonaprop {fecha_formato}.csv"

fecha_extraccion = datetime.now().strftime("%Y-%m-%d")

# Selectores Zonaprop
CARD = "div.postingCard-module__posting-container"
TITLE = "h2.postingLocations-module__location-text"
PRICE = "div.postingPrices-module__price[data-qa='POSTING_CARD_PRICE']"
LOCATION = "h2.postingLocations-module__location-text[data-qa='POSTING_CARD_LOCATION']"
IMG_SELECTOR = "img"


# ================= HELPERS =================

def clean_price(text: str):
    if not text:
        return None
    n = re.sub(r"[^\d]", "", text)
    return int(n) if n.isdigit() else None


def detect_currency(text: str):
    t = text.upper()
    if "USD" in t or "U$S" in t:
        return "USD"
    return "ARS"


def extract_m2(text: str):
    """Busca expresamente un número seguido de m² o m2."""
    m = re.search(r"(\d+)\s*(m²|m2)", text.lower())
    return int(m.group(1)) if m else None


def normalize_separators(text: str):
    SEPARADORES = ["·", "•", "‧", "∙", "⋅", "· ", " ·", " •", "• ", "  ·  ", "  •  "]
    for s in SEPARADORES:
        text = text.replace(s, "|")
    while "||" in text:
        text = text.replace("||", "|")
    return text


def clean_text(text: str):
    if not text:
        return ""
    t = text.replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", t).strip()


def extract_ambientes(text: str):
    """Extrae solo ambientes."""
    m = re.search(r"(\d+)\s*amb", text.lower())
    return int(m.group(1)) if m else None

def contains_any(text, words):
    if not text:
        return False

    t = text.lower()

    return any(w.lower() in t for w in words)


def extract_expensas(text):
    if not text:
        return None

    m = re.search(
        r"\$\s*([\d\.]+)\s*expensas",
        text.lower()
    )

    if not m:
        return None

    return int(
        m.group(1).replace(".", "")
    )


def extract_direccion(text):
    if not text:
        return None

    texto = text.replace("·", "|")
    partes = texto.split("|")

    for p in partes:
        p = p.strip()

        if re.search(r"\d+", p):
            if "capital federal" not in p.lower():
                if "m²" not in p.lower():
                    if "amb" not in p.lower():
                        return p

    return None
# ================= SCRAPING =================

def load_page(page_number: int):
    url = BASE_URL if page_number == 1 else BASE_URL.replace(".html", f"-pagina-{page_number}.html")
    print(f"\n→ Cargando página {page_number}: {url}")

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"   Intento {attempt}/{MAX_RETRIES}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(url)

            try:
                page.wait_for_selector(CARD, timeout=8000)
                cards = page.query_selector_all(CARD)

                if len(cards) > 0:
                    print(f"   ✔ Cards cargadas: {len(cards)}")
                    data = scrape_cards(cards, page_number)
                    browser.close()
                    return data

            except Exception as e:
                print(f"   ⚠ Error: {e}")
                browser.close()
                time.sleep(2)

    print("❌ No se pudo cargar la página.")
    return []


def scrape_cards(cards, page_number: int):
    rows = []

    for c in cards:
        full_raw = c.inner_text()
        texto_limpio = clean_text(full_raw)

direccion = extract_direccion(full_raw)

expensas = extract_expensas(full_raw)

mascotas = contains_any(
    full_raw,
    [
        "acepta mascotas",
        "mascotas",
        "pet friendly"
    ]
)

balcon = contains_any(
    full_raw,
    [
        "balcón",
        "balcon"
    ]
)

cochera = contains_any(
    full_raw,
    [
        "cochera",
        "garage"
    ]
)

apto_profesional = contains_any(
    full_raw,
    [
        "apto profesional"
    ]
)

terraza = contains_any(
    full_raw,
    [
        "terraza"
    ]
)

pileta = contains_any(
    full_raw,
    [
        "pileta",
        "piscina"
    ]
)

        t = c.query_selector(TITLE)
        l = c.query_selector(LOCATION)
        p = c.query_selector(PRICE)
        img_el = c.query_selector(IMG_SELECTOR)

        barrio = l.inner_text().strip() if l else (t.inner_text().strip() if t else "")

        precio_raw = p.inner_text().strip() if p else None
        moneda = detect_currency(precio_raw) if precio_raw else None
        precio_num = clean_price(precio_raw)

        precio_ars = None
        if precio_num:
            precio_ars = precio_num * USD_TO_ARS if moneda == "USD" else precio_num

        if precio_ars and precio_ars > MAX_PRECIO_ARS:
            continue

        # m2 real
        m2 = extract_m2(full_raw)

        # ambientes real
        ambientes = extract_ambientes(full_raw)

        # precio por m2
        precio_m2 = int(round(precio_ars / m2)) if (precio_ars and m2) else None

        # URL de imagen
        url_img = None
        if img_el:
            url_img = img_el.get_attribute("src") or img_el.get_attribute("data-flickity-lazyload")

        rows.append({
    "fecha": fecha_extraccion,
    "pagina": page_number,

    "barrio": barrio,
    "direccion": direccion,

    "precio_raw": precio_raw,
    "moneda": moneda,

    "m2": m2,
    "ambientes": ambientes,

    "precio_m2": precio_m2,

    "mascotas": mascotas,
    "balcon": balcon,
    "cochera": cochera,
    "apto_profesional": apto_profesional,
    "terraza": terraza,
    "pileta": pileta,

    "expensas": expensas,

    "url": url_img,

    "texto": texto_limpio
})

    return rows


# ================= MAIN =================

def main():
    all_rows = []

    for n in PAGES:
        all_rows.extend(load_page(n))

    df = pd.DataFrame(all_rows)

    df.to_csv(
        OUTPUT_FILE,
        sep=";",
        index=False,
        encoding="utf-8-sig"
    )

    print(f"\n✔ Archivo generado correctamente: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
