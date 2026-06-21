import streamlit as st
import pandas as pd
import glob
import os

st.set_page_config(page_title="Dashboard Inmobiliario", layout="wide")


def cargar_ultimo_csv(prefijo):
    archivos = glob.glob(f"{prefijo}*.csv")

    archivos_validos = [
        a for a in archivos
        if os.path.getsize(a) > 0
    ]

    if not archivos_validos:
        return None, None

    archivo = max(archivos_validos, key=os.path.getmtime)

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


def preparar_df(df):
    if df is None:
        return None

    df = df.copy()

    columnas_numericas = [
        "precio_m2",
        "m2",
        "ambientes",
        "expensas",
        "dormitorios",
        "banos",
    ]

    for col in columnas_numericas:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    columnas_bool = [
        "mascotas",
        "balcon",
        "cochera",
        "terraza",
        "pileta",
        "parrilla",
        "luminoso",
    ]

    for col in columnas_bool:
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.lower()
                .isin(["true", "1", "sí", "si"])
            )

    if "imagen" in df.columns:
        df["imagen"] = df["imagen"].apply(lambda x: x if es_url_valida(x) else None)
        df.loc[
            df["imagen"]
            .astype(str)
            .str.contains("/empresas/|logo", case=False, na=False),
            "imagen",
        ] = None

    if "url" in df.columns:
        df["url"] = df["url"].apply(lambda x: x if es_url_valida(x) else None)

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
            df["score_precio"] = 35 * (
                1 - ((df["precio_m2"] - min_pm2) / (max_pm2 - min_pm2))
            )
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
        df["score"] += df["m2"].apply(
            lambda x: 3 if pd.notna(x) and x >= promedio_m2 else 0
        )

    df["score"] = df["score"].round(0).clip(0, 100).astype(int)

    return df


def aplicar_filtros(df, key_prefix):
    st.sidebar.header("Filtros")

    if "barrio" in df.columns:
        barrios = sorted(df["barrio"].dropna().unique())

        barrio = st.sidebar.selectbox(
            "Barrio",
            ["Todos"] + barrios,
            key=f"{key_prefix}_barrio",
        )

        if barrio != "Todos":
            df = df[df["barrio"] == barrio]

    if "ambientes" in df.columns:
        ambientes = st.sidebar.multiselect(
            "Ambientes",
            sorted(df["ambientes"].dropna().unique()),
            key=f"{key_prefix}_ambientes",
        )

        if ambientes:
            df = df[df["ambientes"].isin(ambientes)]

    if "m2" in df.columns and df["m2"].notna().any():
        min_m2 = int(df["m2"].min())
        max_m2 = int(df["m2"].max())

        if min_m2 < max_m2:
            m2_min = st.sidebar.slider(
                "M² mínimo",
                min_m2,
                max_m2,
                min_m2,
                key=f"{key_prefix}_m2",
            )
            df = df[df["m2"] >= m2_min]
        else:
            st.sidebar.info(f"M² único disponible: {min_m2}")

    if "precio_m2" in df.columns and df["precio_m2"].notna().any():
        min_pm2 = int(df["precio_m2"].min())
        max_pm2 = int(df["precio_m2"].max())

        if min_pm2 < max_pm2:
            pm2_max = st.sidebar.slider(
                "Precio m² máximo",
                min_pm2,
                max_pm2,
                max_pm2,
                key=f"{key_prefix}_pm2",
            )
            df = df[df["precio_m2"] <= pm2_max]
        else:
            st.sidebar.info(f"Precio m² único: $ {min_pm2:,}".replace(",", "."))

    for col, label in [
        ("mascotas", "Acepta mascotas"),
        ("balcon", "Con balcón"),
        ("cochera", "Con cochera"),
        ("terraza", "Con terraza"),
        ("pileta", "Con pileta"),
        ("parrilla", "Con parrilla"),
        ("luminoso", "Luminoso"),
    ]:
        if col in df.columns:
            if st.sidebar.checkbox(label, key=f"{key_prefix}_{col}"):
                df = df[df[col] == True]

    return df


def texto_corto(valor, limite=180):
    if pd.isna(valor):
        return ""

    texto = str(valor)
    return texto[:limite] + "..." if len(texto) > limite else texto


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

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Propiedades", len(df_filtrado))

    if "score" in df_filtrado.columns:
        c2.metric("Score promedio", int(df_filtrado["score"].mean()))

    if "precio_m2" in df_filtrado.columns and df_filtrado["precio_m2"].notna().any():
        c3.metric(
            "Promedio $/m²",
            f"$ {int(df_filtrado['precio_m2'].mean()):,}".replace(",", "."),
        )

    if "m2" in df_filtrado.columns and df_filtrado["m2"].notna().any():
        c4.metric("Promedio m²", round(df_filtrado["m2"].mean(), 1))

    column_config = {
        "url": st.column_config.LinkColumn("Aviso", display_text="Abrir"),
        "imagen": st.column_config.ImageColumn("Imagen"),
        "score": st.column_config.ProgressColumn(
            "Score",
            min_value=0,
            max_value=100,
        ),
    }

    if "precio_m2" in df_filtrado.columns:
        column_config["precio_m2"] = st.column_config.NumberColumn(
            "Precio m²",
            format="$ %d",
        )

    st.subheader("🏆 Mejores oportunidades por score")

    sort_cols = ["score"]
    ascending = [False]

    if "precio_m2" in df_filtrado.columns:
        sort_cols.append("precio_m2")
        ascending.append(True)

    top_score = (
        df_filtrado
        .sort_values(
            by=sort_cols,
            ascending=ascending,
            na_position="last",
        )
        .head(12)
    )

    cols = st.columns(3)

    for i, (_, row) in enumerate(top_score.iterrows()):
        with cols[i % 3]:
            imagen = row.get("imagen", None)

            if es_url_valida(imagen):
                st.image(imagen, use_container_width=True)

            st.markdown(f"### {row.get('barrio', '')}")

            direccion = str(row.get("direccion", "") or "")
            texto_desc = str(row.get("texto", "") or "")

            st.write(texto_corto(direccion, 170))

            with st.expander("Ver más"):
                if direccion:
                    st.write(direccion)
                if texto_desc:
                    st.write(texto_desc)

            st.markdown(f"**Precio:** {row.get('precio_raw', '')}")
            st.markdown(f"**M²:** {row.get('m2', '')}")

            if "precio_m2" in row and pd.notna(row.get("precio_m2", None)):
                st.markdown(
                    f"**Precio/m²:** $ {int(row['precio_m2']):,}".replace(",", ".")
                )
            else:
                st.markdown("**Precio/m²:** -")

            st.markdown(f"**Score:** {row.get('score', 0)}")

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
                st.caption(" · ".join(amenities))

            url = row.get("url", None)

            if es_url_valida(url):
                st.link_button("Ver aviso", url)

    st.subheader("🔥 Top 20 menor precio por m²")

    if "precio_m2" in df_filtrado.columns:
        top_pm2 = (
            df_filtrado
            .dropna(subset=["precio_m2"])
            .sort_values("precio_m2", ascending=True)
            .head(20)
        )
    else:
        top_pm2 = pd.DataFrame()

    if top_pm2.empty:
        st.info("No hay datos suficientes para calcular el Top 20 por precio/m².")
    else:
        st.dataframe(
            top_pm2,
            use_container_width=True,
            column_config=column_config,
        )

    st.subheader("📋 Todas las propiedades")

    st.dataframe(
        df_filtrado,
        use_container_width=True,
        column_config=column_config,
    )


tab1, tab2 = st.tabs(["🏠 Zonaprop", "🟡 MercadoLibre"])

with tab1:
    df_zona, archivo_zona = cargar_ultimo_csv("zonaprop")
    mostrar_dashboard(df_zona, archivo_zona, "🏠 Dashboard Zonaprop")

with tab2:
    df_meli, archivo_meli = cargar_ultimo_csv("mercadolibre")
    mostrar_dashboard(df_meli, archivo_meli, "🟡 Dashboard MercadoLibre")