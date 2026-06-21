import streamlit as st
import pandas as pd
import glob
import os
import re

st.set_page_config(
    page_title="Dashboard Inmobiliario",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =====================
# CSS
# =====================

st.markdown("""
<style>
.stApp {
    background: #ffffff !important;
    color: #1f2937 !important;
}

.block-container {
    padding-top: 1rem;
    padding-left: 1rem;
    padding-right: 1rem;
}

h1, h2, h3, p, span, div {
    color: #1f2937;
}

.property-card {
    border: 1px solid #e5e7eb;
    border-radius: 18px;
    padding: 18px;
    margin-bottom: 18px;
    background: #ffffff;
    box-shadow: 0 4px 14px rgba(0,0,0,0.06);
}

.property-title {
    font-size: 1.35rem;
    font-weight: 800;
    margin-bottom: 8px;
}

.property-text {
    color: #4b5563;
    line-height: 1.45;
    margin-bottom: 10px;
}

.badge {
    display: inline-block;
    padding: 5px 10px;
    margin: 3px 4px 3px 0;
    border-radius: 999px;
    background: #f3f4f6;
    color: #374151;
    font-size: 0.85rem;
    font-weight: 600;
}

.score-pill {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 999px;
    background: #ede9fe;
    color: #5b21b6;
    font-weight: 800;
    margin-top: 6px;
}

.ver-mas {
    color: #7c3aed;
    font-weight: 700;
    margin-top: 8px;
}

[data-testid="stExpander"] {
    border: none !important;
    box-shadow: none !important;
    background: transparent !important;
}

[data-testid="stExpander"] summary {
    color: #7c3aed !important;
    font-weight: 700 !important;
}

[data-testid="stMetricValue"] {
    font-size: 1.7rem;
}

@media (max-width: 768px) {
    h1 {
        font-size: 2rem !important;
    }

    h2, h3 {
        font-size: 1.35rem !important;
    }

    .property-card {
        padding: 14px;
        border-radius: 14px;
    }

    .property-title {
        font-size: 1.2rem;
    }

    [data-testid="stDataFrame"] {
        font-size: 0.8rem;
    }
}
</style>
""", unsafe_allow_html=True)


# =====================
# HELPERS
# =====================

def cargar_ultimo_csv(prefijo):
    archivos = [
        a for a in glob.glob(f"{prefijo}*.csv")
        if os.path.getsize(a) > 0
        and "detallado" not in a.lower()
    ]

    if not archivos:
        return None, None

    archivo = max(archivos, key=os.path.getmtime)

    try:
        df = pd.read_csv(archivo, sep=";")
        if df.empty:
            return None, archivo
        return df, archivo
    except Exception:
        return None, archivo


def es_url_valida(valor):
    if pd.isna(valor):
        return False
    v = str(valor).strip().lower()
    return v.startswith("http") and v not in ["nan", "none", ""]


def normalizar_texto(valor):
    if pd.isna(valor):
        return ""
    texto = str(valor).lower()
    texto = re.sub(r"[^a-z0-9áéíóúñ ]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def normalizar_direccion(valor):
    texto = normalizar_texto(valor)

    cortes = [
        "capital federal",
        "departamento",
        "alquiler",
        "excelente",
        "hermoso",
        "oportunidad",
        "contacto",
        "whatsapp",
        "corredor responsable",
    ]

    for corte in cortes:
        if corte in texto:
            texto = texto.split(corte)[0].strip()

    texto = re.sub(r"\b(caba|cap fed)\b", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()

    return texto


def preparar_df(df):
    if df is None:
        return None

    df = df.copy()

    for col in ["precio_m2", "m2", "ambientes", "expensas", "dormitorios", "banos"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["mascotas", "balcon", "cochera", "terraza", "pileta", "parrilla", "luminoso"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().isin(["true", "1", "sí", "si"])

    if "imagen" in df.columns:
        df["imagen"] = df["imagen"].apply(lambda x: x if es_url_valida(x) else None)
        df.loc[
            df["imagen"].astype(str).str.contains("/empresas/|logo", case=False, na=False),
            "imagen"
        ] = None

    if "url" in df.columns:
        df["url"] = df["url"].apply(lambda x: x if es_url_valida(x) else None)

    if "direccion" in df.columns:
        df["direccion_normalizada"] = df["direccion"].apply(normalizar_direccion)

        if "precio_m2" in df.columns:
            df = (
                df.sort_values(["direccion_normalizada", "precio_m2"], ascending=[True, True])
                .drop_duplicates(subset=["direccion_normalizada"], keep="first")
            )
        else:
            df = df.drop_duplicates(subset=["direccion_normalizada"], keep="first")

    return df


def score_barrio(valor):
    if pd.isna(valor):
        return 50

    barrio = str(valor).lower()

    scores = {
        "villa santa rita": 90,
        "villa general mitre": 90,
        "flores": 85,
        "la paternal": 80,
        "floresta": 80,
        "caballito": 75,
        "villa del parque": 70,
        "villa devoto": 70,
    }

    for zona, score in scores.items():
        if zona in barrio:
            return score

    return 50


def calcular_score(df):
    if df is None or df.empty:
        return df

    df = df.copy()
    df["score"] = 0

    if "barrio" in df.columns:
        df["score_barrio"] = df["barrio"].apply(score_barrio)
        df["score"] += df["score_barrio"] * 0.40

    if "precio_m2" in df.columns and df["precio_m2"].notna().any():
        max_pm2 = df["precio_m2"].max()
        min_pm2 = df["precio_m2"].min()

        if max_pm2 > min_pm2:
            df["score_precio"] = 35 * (1 - ((df["precio_m2"] - min_pm2) / (max_pm2 - min_pm2)))
        else:
            df["score_precio"] = 20

        df["score"] += df["score_precio"].fillna(0)

    pesos = {
        "cochera": 8,
        "balcon": 6,
        "mascotas": 6,
        "terraza": 5,
        "parrilla": 4,
        "pileta": 4,
        "luminoso": 4,
    }

    for col, peso in pesos.items():
        if col in df.columns:
            df["score"] += df[col].astype(bool) * peso

    if "m2" in df.columns and df["m2"].notna().any():
        promedio_m2 = df["m2"].mean()
        df["score"] += df["m2"].apply(lambda x: 3 if pd.notna(x) and x >= promedio_m2 else 0)

    df["score"] = df["score"].round(0).clip(0, 100).astype(int)

    return df


def aplicar_filtros(df, key_prefix):
    with st.expander("🔎 Filtros", expanded=False):
        if "barrio" in df.columns:
            barrios = sorted(df["barrio"].dropna().unique())
            barrio = st.selectbox("Barrio", ["Todos"] + barrios, key=f"{key_prefix}_barrio")
            if barrio != "Todos":
                df = df[df["barrio"] == barrio]

        if "ambientes" in df.columns:
            ambientes = st.multiselect(
                "Ambientes",
                sorted(df["ambientes"].dropna().unique()),
                key=f"{key_prefix}_ambientes"
            )
            if ambientes:
                df = df[df["ambientes"].isin(ambientes)]

        if "m2" in df.columns and df["m2"].notna().any():
            min_m2 = int(df["m2"].min())
            max_m2 = int(df["m2"].max())
            if min_m2 < max_m2:
                m2_min = st.slider("M² mínimo", min_m2, max_m2, min_m2, key=f"{key_prefix}_m2")
                df = df[df["m2"] >= m2_min]

        if "precio_m2" in df.columns and df["precio_m2"].notna().any():
            min_pm2 = int(df["precio_m2"].min())
            max_pm2 = int(df["precio_m2"].max())
            if min_pm2 < max_pm2:
                pm2_max = st.slider("Precio m² máximo", min_pm2, max_pm2, max_pm2, key=f"{key_prefix}_pm2")
                df = df[df["precio_m2"] <= pm2_max]

        col1, col2 = st.columns(2)

        filtros = [
            ("mascotas", "🐶 Mascotas"),
            ("balcon", "🌿 Balcón"),
            ("cochera", "🚗 Cochera"),
            ("terraza", "☀️ Terraza"),
            ("pileta", "🏊 Pileta"),
            ("parrilla", "🔥 Parrilla"),
            ("luminoso", "💡 Luminoso"),
        ]

        for i, (col, label) in enumerate(filtros):
            if col in df.columns:
                with col1 if i % 2 == 0 else col2:
                    if st.checkbox(label, key=f"{key_prefix}_{col}"):
                        df = df[df[col] == True]

    return df


def texto_corto(valor, limite=150):
    if pd.isna(valor):
        return ""
    texto = str(valor)
    return texto[:limite] + "..." if len(texto) > limite else texto


def formato_money(valor):
    if pd.isna(valor):
        return "-"
    return f"$ {int(valor):,}".replace(",", ".")


def render_card(row):
    barrio = row.get("barrio", "")
    direccion = str(row.get("direccion", "") or "")
    texto_desc = str(row.get("texto", "") or "")
    imagen = row.get("imagen", None)
    url = row.get("url", None)

    st.markdown('<div class="property-card">', unsafe_allow_html=True)

    if es_url_valida(imagen):
        st.image(imagen, use_container_width=True)

    st.markdown(f'<div class="property-title">{barrio}</div>', unsafe_allow_html=True)

    if direccion:
        st.markdown(f'<div class="property-text">{texto_corto(direccion, 150)}</div>', unsafe_allow_html=True)

    with st.expander("Ver más"):
        if direccion:
            st.write(direccion)
        if texto_desc:
            st.write(texto_desc)

    st.markdown(f"**Precio:** {row.get('precio_raw', '-')}")
    st.markdown(f"**M²:** {row.get('m2', '-')}")
    st.markdown(f"**Precio/m²:** {formato_money(row.get('precio_m2', None))}")
    st.markdown(f'<div class="score-pill">Score: {row.get("score", 0)}</div>', unsafe_allow_html=True)

    amenities = []
    for col, label in [
        ("cochera", "🚗 Cochera"),
        ("balcon", "🌿 Balcón"),
        ("mascotas", "🐶 Mascotas"),
        ("terraza", "☀️ Terraza"),
        ("parrilla", "🔥 Parrilla"),
        ("pileta", "🏊 Pileta"),
        ("luminoso", "💡 Luminoso"),
    ]:
        if col in row and row[col] == True:
            amenities.append(label)

    if amenities:
        badges = "".join([f'<span class="badge">{x}</span>' for x in amenities])
        st.markdown(badges, unsafe_allow_html=True)

    if es_url_valida(url):
        st.link_button("Ver aviso", url, use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)


def mostrar_dashboard(df, archivo, titulo):
    if df is None:
        st.warning(f"No encontré CSV para {titulo}.")
        return

    df = preparar_df(df)
    df = calcular_score(df)

    st.title(titulo)
    st.caption(f"Archivo cargado: {archivo}")

    df_filtrado = aplicar_filtros(df, titulo)

    if df_filtrado.empty:
        st.warning("No hay propiedades con los filtros actuales.")
        return

    k1, k2, k3 = st.columns(3)

    k1.metric("Propiedades", len(df_filtrado))

    if "score" in df_filtrado.columns:
        k2.metric("Score promedio", int(df_filtrado["score"].mean()))

    if "precio_m2" in df_filtrado.columns and df_filtrado["precio_m2"].notna().any():
        k3.metric("Promedio $/m²", formato_money(df_filtrado["precio_m2"].mean()))

    st.subheader("🏆 Mejores oportunidades")

    sort_cols = ["score"]
    ascending = [False]

    if "precio_m2" in df_filtrado.columns:
        sort_cols.append("precio_m2")
        ascending.append(True)

    top_score = (
        df_filtrado
        .sort_values(by=sort_cols, ascending=ascending, na_position="last")
        .head(8)
    )

    for _, row in top_score.iterrows():
        render_card(row)

    st.subheader("🔥 Top 20 menor precio por m²")

    if "precio_m2" in df_filtrado.columns:
        columnas_top = [
            c for c in [
                "barrio",
                "direccion",
                "precio_raw",
                "m2",
                "precio_m2",
                "score",
                "url",
            ]
            if c in df_filtrado.columns
        ]

        top_pm2 = (
            df_filtrado
            .dropna(subset=["precio_m2"])
            .sort_values("precio_m2", ascending=True)
            .head(20)
        )

        if top_pm2.empty:
            st.info("No hay datos suficientes para calcular el Top 20.")
        else:
            st.dataframe(
                top_pm2[columnas_top],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "url": st.column_config.LinkColumn("Aviso", display_text="Abrir"),
                    "precio_m2": st.column_config.NumberColumn("Precio m²", format="$ %d"),
                    "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
                }
            )

    st.subheader("📋 Todas las propiedades")

    columnas_tabla = [
        c for c in [
            "barrio",
            "direccion",
            "precio_raw",
            "m2",
            "ambientes",
            "dormitorios",
            "banos",
            "precio_m2",
            "score",
            "mascotas",
            "balcon",
            "cochera",
            "terraza",
            "url",
        ]
        if c in df_filtrado.columns
    ]

    st.dataframe(
        df_filtrado[columnas_tabla],
        use_container_width=True,
        hide_index=True,
        column_config={
            "url": st.column_config.LinkColumn("Aviso", display_text="Abrir"),
            "precio_m2": st.column_config.NumberColumn("Precio m²", format="$ %d"),
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
        }
    )


tab1, tab2 = st.tabs(["🏠 Zonaprop", "🟡 MercadoLibre"])

with tab1:
    df_zona, archivo_zona = cargar_ultimo_csv("zonaprop")
    mostrar_dashboard(df_zona, archivo_zona, "🏠 Dashboard Zonaprop")

with tab2:
    st.info("MercadoLibre pausado por captcha / detección bot. Cuando tengamos un CSV limpio, se activa acá.")