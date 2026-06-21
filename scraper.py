from playwright.sync_api import sync_playwright
import pandas as pd
from datetime import datetime
import re
import time
import os

# ================= CONFIG =================

BASE_URL = "https://www.zonaprop.com.ar/inmuebles-alquiler-capital-federal-villa-devoto-villa-santa-rita-villa-general-mitre-villa-del-parque-villa-luro-la-paternal-caballito-flores-floresta-con-balcon-4-ambientes.html"

PAGES = list(range(1, 6))
MAX_PRECIO_ARS = 2_000_000
USD_TO_ARS = 1500
MAX_RETRIES = 3

fecha_extraccion = datetime.now().strftime("%Y-%m-%d")
OUTPUT_FILE = "zonaprop_actual.csv"

HEADLESS = True if os.getenv("GITHUB_ACTIONS") == "true" else False

CARD = "div.postingCard-module__posting-container"

BARRIOS_VALIDOS = sorted([
    "Villa General Mitre",
    "Villa Santa Rita",
    "Villa del Parque",
    "Villa Devoto",
    "Villa Luro",
    "Floresta Norte",
    "Floresta Sur",
    "La Paternal",
    "Caballito",
    "Floresta",
    "Flores",
], key=len, reverse=True)


# ================= HELPERS =================

def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\n", " ").replace("\r", " ")).strip()


def contains_any(text, keywords):
    if not text:
        return False
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def acepta_mascotas(texto):
    if not texto:
        return False

    t = texto.lower()

    negativos = [
        "no se aceptan mascotas",
        "no se acepta mascotas",
        "no acepta mascotas",
        "no aceptan mascotas",
        "no mascotas",
        "sin mascotas",
    ]

    if any(n in t for n in negativos):
        return False

    positivos = [
        "acepta mascotas",
        "se aceptan mascotas",
        "mascotas",
        "pet friendly",
        "permite mascotas",
    ]

    return any(p in t for p in positivos)


def normalizar_barrio(barrio):
    if not barrio:
        return None

    b = str(barrio).lower()

    if "villa santa rita" in b:
        return "Villa Santa Rita"
    if "villa general mitre" in b:
        return "Villa General Mitre"
    if "villa del parque" in b:
        return "Villa del Parque"
    if "villa devoto" in b:
        return "Villa Devoto"
    if "villa luro" in b:
        return "Villa Luro"
    if "la paternal" in b:
        return "La Paternal"
    if "floresta norte" in b:
        return "Floresta"
    if "floresta sur" in b:
        return "Floresta"
    if "floresta" in b:
        return "Floresta"
    if "flores" in b:
        return "Flores"
    if "caballito" in b:
        return "Caballito"

    return barrio


def detectar_barrio(texto):
    if not texto:
        return None

    t = str(texto).lower()

    for barrio in BARRIOS_VALIDOS:
        if barrio.lower() in t:
            return normalizar_barrio(barrio)

    return None


def limpiar_direccion(direccion):
    if not direccion:
        return None

    d = clean_text(direccion)

    d = re.sub(r"^\s*\d+\s*coch\.?\s*", "", d, flags=re.I)
    d = re.sub(r"^\s*coch\.?\s*", "", d, flags=re.I)
    d = re.sub(r"^\s*cochera\s*", "", d, flags=re.I)
    d = re.sub(r"^\s*garage\s*", "", d, flags=re.I)

    cortes = [
        "Departamento",
        "Alquiler",
        "Excelente",
        "Hermoso",
        "Muy",
        "Oportunidad",
        "Disponible",
        "Contacto",
        "WhatsApp",
        "Super destacado",
        "Destacado",
        "Corredor Responsable",
    ]

    for corte in cortes:
        idx = d.lower().find(corte.lower())
        if idx > 8:
            d = d[:idx].strip()
            break

    return d.strip() if d.strip() else None


def parsear_texto_propiedad(texto):
    t = clean_text(texto)

    moneda = "USD" if re.search(r"\b(USD|U\$S)\b", t, re.I) else "ARS"

    precio_raw = None
    precio_num = None

    if moneda == "USD":
        m = re.search(r"(USD|U\$S)\s*([\d\.]+)", t, re.I)
        if m:
            precio_raw = f"USD {m.group(2)}"
            precio_num = int(m.group(2).replace(".", ""))
    else:
        m = re.search(r"\$\s*([\d\.]+)", t)
        if m:
            precio_raw = f"$ {m.group(1)}"
            precio_num = int(m.group(1).replace(".", ""))

    expensas = None
    m_exp = re.search(r"\$\s*([\d\.]+)\s*Expensas", t, re.I)
    if m_exp:
        expensas = int(m_exp.group(1).replace(".", ""))

    m2 = None
    m_m2 = re.search(r"(\d+)\s*m²", t, re.I)
    if m_m2:
        m2 = int(m_m2.group(1))

    ambientes = None
    m_amb = re.search(r"(\d+)\s*amb", t, re.I)
    if m_amb:
        ambientes = int(m_amb.group(1))

    dormitorios = None
    m_dorm = re.search(r"(\d+)\s*dorm", t, re.I)
    if m_dorm:
        dormitorios = int(m_dorm.group(1))

    banos = None
    m_banos = re.search(r"(\d+)\s*bañ", t, re.I)
    if m_banos:
        banos = int(m_banos.group(1))

    cochera = bool(re.search(r"\bcoch\.?\b|\bcochera\b|\bgarage\b", t, re.I))

    direccion = None

    m_dir = re.search(
        r"(?:\d+\s*bañ(?:o|os)?\.?|baño|baños|coch\.?|cochera|garage)\s+(.+)",
        t,
        re.I
    )

    if m_dir:
        direccion = m_dir.group(1).strip()

    if not direccion:
        posibles = re.split(r"[·•‧∙⋅]", t)

        for p in posibles:
            p = p.strip()
            low = p.lower()

            if (
                re.search(r"\d+", p)
                and "$" not in p
                and "expensas" not in low
                and "m²" not in low
                and "m2" not in low
                and "amb" not in low
                and "dorm" not in low
                and "bañ" not in low
            ):
                direccion = p
                break

    direccion = limpiar_direccion(direccion)

    return {
        "precio_raw": precio_raw,
        "precio_num": precio_num,
        "moneda": moneda,
        "expensas": expensas,
        "m2": m2,
        "ambientes": ambientes,
        "dormitorios": dormitorios,
        "banos": banos,
        "cochera": cochera,
        "direccion": direccion,
    }


def extract_real_url(card):
    try:
        for a in card.query_selector_all("a"):
            href = a.get_attribute("href")
            if href and "/propiedades/" in href:
                return "https://www.zonaprop.com.ar" + href if href.startswith("/") else href
    except Exception:
        pass

    return None


def extract_image_url(card):
    try:
        imgs = card.query_selector_all("img")

        for img in imgs:
            src = (
                img.get_attribute("src")
                or img.get_attribute("data-src")
                or img.get_attribute("data-flickity-lazyload")
                or ""
            )

            alt = (img.get_attribute("alt") or "").lower()
            src_lower = src.lower()

            if not src:
                continue

            if "/empresas/" in src_lower:
                continue

            if "logo" in src_lower or "logo" in alt:
                continue

            if "/avisos/" in src_lower:
                return src

        return None

    except Exception:
        return None


def build_page_url(page_number):
    return BASE_URL if page_number == 1 else BASE_URL.replace(".html", f"-pagina-{page_number}.html")


# ================= SCRAPER =================

def scrape_cards(cards, page_number):
    rows = []

    for card in cards:
        texto = clean_text(card.inner_text())
        datos = parsear_texto_propiedad(texto)

        barrio_detectado = (
            detectar_barrio(texto)
            or detectar_barrio(datos.get("direccion"))
        )

        precio_num = datos["precio_num"]
        moneda = datos["moneda"]

        precio_ars = None
        if precio_num:
            precio_ars = precio_num * USD_TO_ARS if moneda == "USD" else precio_num

        if precio_ars and precio_ars > MAX_PRECIO_ARS:
            continue

        m2 = datos["m2"]
        precio_m2 = int(round(precio_ars / m2)) if precio_ars and m2 else None

        rows.append({
            "fecha": fecha_extraccion,
            "pagina": page_number,
            "barrio": barrio_detectado,
            "direccion": datos["direccion"],
            "precio_raw": datos["precio_raw"],
            "moneda": moneda,
            "expensas": datos["expensas"],
            "m2": m2,
            "ambientes": datos["ambientes"],
            "dormitorios": datos["dormitorios"],
            "banos": datos["banos"],
            "precio_m2": precio_m2,
            "mascotas": acepta_mascotas(texto),
            "balcon": contains_any(texto, ["balcón", "balcon"]),
            "cochera": datos["cochera"],
            "terraza": contains_any(texto, ["terraza"]),
            "pileta": contains_any(texto, ["pileta", "piscina"]),
            "parrilla": contains_any(texto, ["parrilla"]),
            "luminoso": contains_any(texto, ["luminoso", "luminosa"]),
            "url": extract_real_url(card),
            "imagen": extract_image_url(card),
            "texto": texto,
        })

    return rows


def load_page(page_number):
    url = build_page_url(page_number)
    print(f"\n→ Cargando página {page_number}: {url}")

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"   Intento {attempt}/{MAX_RETRIES}")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=HEADLESS,
                args=["--disable-dev-shm-usage"]
            )

            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(6000)

                for _ in range(5):
                    page.mouse.wheel(0, 1200)
                    page.wait_for_timeout(1200)

                cards = page.query_selector_all(CARD)

                if not cards:
                    cards = page.query_selector_all("div[class*='posting']")

                if cards:
                    print(f"   ✔ Cards encontradas: {len(cards)}")
                    data = scrape_cards(cards, page_number)
                    browser.close()
                    return data

                print("   ⚠ No se encontraron cards")

            except Exception as e:
                print(f"   ⚠ Error: {e}")

            finally:
                browser.close()
                time.sleep(3)

    print(f"   ❌ Página {page_number} omitida")
    return []


def main():
    all_rows = []

    for page_number in PAGES:
        all_rows.extend(load_page(page_number))

    df = pd.DataFrame(all_rows)

    if df.empty:
        print("\n❌ No se encontraron propiedades. No se sobrescribe el CSV anterior.")
        return

    columnas = [
        "fecha",
        "pagina",
        "barrio",
        "direccion",
        "precio_raw",
        "moneda",
        "expensas",
        "m2",
        "ambientes",
        "dormitorios",
        "banos",
        "precio_m2",
        "mascotas",
        "balcon",
        "cochera",
        "terraza",
        "pileta",
        "parrilla",
        "luminoso",
        "url",
        "imagen",
        "texto",
    ]

    df = df.reindex(columns=columnas)

    df.to_csv(
        OUTPUT_FILE,
        sep=";",
        index=False,
        encoding="utf-8-sig"
    )

    print(f"\n✔ Archivo generado correctamente: {OUTPUT_FILE}")
    print(f"✔ Total propiedades: {len(df)}")

    print("\nBarrios detectados:")
    print(df["barrio"].value_counts(dropna=False))


if __name__ == "__main__":
    main()
