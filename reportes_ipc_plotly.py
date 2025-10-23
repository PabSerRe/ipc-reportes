import pandas as pd
import streamlit as st
import plotly.express as px
import os

st.set_page_config(page_title="Reportes IPC – Plotly", layout="wide")

# OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../../outputs")
# os.makedirs(OUTPUT_DIR, exist_ok=True)

@st.cache_data
def cargar_datos():
    df = pd.read_csv("../../data/ipc_maestro_sin_ponderaciones.csv")
    df["fecha"] = pd.to_datetime(df["fecha"].astype(str).str[:7], errors="coerce")

    # --- Calcular Región Nacional ---
    pesos = {
        "Región GBA": 0.449,
        "Región Pampeana": 0.319,
        "Región Noroeste": 0.083,
        "Región Noreste": 0.080,
        "Región Cuyo": 0.049,
        "Región Patagonia": 0.020,
    }
    factor = sum(pesos.values())
    pesos = {k: v / factor for k, v in pesos.items()}

    base = df[df["region"].isin(pesos.keys())].copy()

    def calc_nacional(g):
        return sum(g["indice"] * g["region"].map(pesos))

    ipc_nacional = (
        base.groupby(["fecha", "categoria", "origen"])
        .apply(calc_nacional)
        .reset_index(name="indice")
    )

    ipc_nacional = ipc_nacional.sort_values("fecha")
    ipc_nacional["variacion_mensual"] = ipc_nacional.groupby(["categoria", "origen"])["indice"].pct_change() * 100
    ipc_nacional["variacion_interanual"] = ipc_nacional.groupby(["categoria", "origen"])["indice"].pct_change(12) * 100
    ipc_nacional["region"] = "Región Nacional"

    df = pd.concat([df, ipc_nacional], ignore_index=True)
    return df

df = cargar_datos()

st.sidebar.header("Filtros")

origen = st.sidebar.selectbox("Origen", sorted(df["origen"].dropna().unique()))
base_origen = df[df["origen"] == origen].copy()

INDICADORES = {
    "variaciones": ["variacion_mensual", "variacion_interanual", "indice"],
    "precios": ["precio_promedio"],
    "aperturas": ["indice"],
}
indicadores_disponibles = INDICADORES.get(origen, [])
if not indicadores_disponibles:
    st.warning("Este origen no tiene indicadores configurados.")
    st.stop()

columna = st.sidebar.selectbox("Indicador a graficar", indicadores_disponibles)

# --- Región por defecto: Nacional ---
regiones = sorted(base_origen["region"].dropna().unique())
if "Región Nacional" in regiones:
    idx_region = regiones.index("Región Nacional")
elif "Región GBA" in regiones:
    idx_region = regiones.index("Región GBA")
else:
    idx_region = 0

region = st.sidebar.selectbox("Región", regiones, index=idx_region)

# --- Categoría por defecto: Nivel general ---
base_region = base_origen[base_origen["region"] == region]
categorias = sorted(base_region["categoria"].dropna().unique())
if "Nivel general" in categorias:
    idx_categoria = categorias.index("Nivel general")
else:
    idx_categoria = 0

categoria = st.sidebar.selectbox("Categoría", categorias, index=idx_categoria)

grafico = st.sidebar.radio(
    "Tipo de gráfico",
    ["Serie temporal", "Comparación regional", "Heatmap", "Acumulado entre fechas"]
)

st.header(f"{grafico} – {categoria} / {region} / {columna} ({origen})")

# === SERIE TEMPORAL ===
if grafico == "Serie temporal":
    base = (
        df[(df["origen"] == origen) & (df["region"] == region) & (df["categoria"] == categoria)]
        .dropna(subset=[columna])
        .copy()
    ).sort_values("fecha")

    fechas_disp = pd.to_datetime(sorted(base["fecha"].unique()))
    if len(fechas_disp) == 0:
        st.warning("No hay datos para esta combinación.")
        st.stop()

    # --- Selectores de fechas ---
    fechas_str_asc = pd.Series(fechas_disp).dt.strftime("%Y-%m").tolist()

    if columna == "variacion_interanual":
        # "Desde": todas las fechas
        desde_str = st.sidebar.selectbox("Desde", fechas_str_asc, index=0)
        desde_dt = pd.to_datetime(desde_str)
        mes_ref = desde_dt.month
        anio_desde = desde_dt.year

        # "Hasta": solo ese mes, años posteriores
        fechas_hasta = [
            f for f in fechas_str_asc
            if f.endswith(f"-{mes_ref:02d}") and pd.to_datetime(f).year > anio_desde
        ]
        if not fechas_hasta:
            st.warning("No hay años posteriores con ese mismo mes.")
            st.stop()

        hasta_str = st.sidebar.selectbox("Hasta", fechas_hasta, index=len(fechas_hasta) - 1)
        hasta_dt = pd.to_datetime(hasta_str)

        # --- Filtrar datos: solo ese mes, entre los años elegidos ---
        datos = base[
            (base["fecha"].dt.month == mes_ref) &
            (base["fecha"].dt.year >= anio_desde) &
            (base["fecha"].dt.year <= hasta_dt.year)
        ].sort_values("fecha")

    else:
        # comportamiento normal
        fechas_str_desc = list(reversed(fechas_str_asc))
        desde_str = st.sidebar.selectbox("Desde", fechas_str_asc, index=0)
        hasta_str = st.sidebar.selectbox("Hasta", fechas_str_desc, index=0)
        desde_dt = pd.to_datetime(desde_str)
        hasta_dt = pd.to_datetime(hasta_str)

        if hasta_dt < desde_dt:
            desde_dt, hasta_dt = hasta_dt, desde_dt

        datos = base[(base["fecha"] >= desde_dt) & (base["fecha"] <= hasta_dt)].sort_values("fecha")

    if datos.empty:
        st.warning("No hay datos para esta selección.")
    else:
        fig = px.line(
            datos,
            x="fecha",
            y=columna,
            markers=True,
            title=f"Evolución {columna} – {categoria} en {region} ({origen})"
        )

        if columna in ["variacion_mensual", "variacion_interanual"]:
            fig.update_traces(
                text=[f"{v:.2f}%" for v in datos[columna]],
                textposition="top center",
                textfont=dict(size=13, color="black"),
                mode="lines+markers+text"
            )
        else:
            valor_inicio = datos[columna].iloc[0]
            valor_final = datos[columna].iloc[-1]
            variacion_pct = (valor_final / valor_inicio - 1) * 100
            fig.add_annotation(
                text=f"Variación total: {variacion_pct:.2f}%",
                xref="paper", yref="paper", x=0.5, y=1.1, showarrow=False,
                font=dict(size=14, color="black", family="Arial")
            )

        st.plotly_chart(fig, use_container_width=True, key=f"serie_temporal_{region}_{categoria}_{columna}")

# === ACUMULADO ENTRE FECHAS ===
elif grafico == "Acumulado entre fechas":
    base = (
        df[(df["origen"] == origen) & (df["region"] == region) & (df["categoria"] == categoria)]
        .dropna(subset=["indice"])
        .copy()
    ).sort_values("fecha")

    if base.empty:
        st.warning("No hay datos de índice disponibles para esta combinación.")
        st.stop()

    fechas_disp = pd.to_datetime(sorted(base["fecha"].unique()))
    fechas_str_asc = pd.Series(fechas_disp).dt.strftime("%Y-%m").tolist()
    fechas_str_desc = list(reversed(fechas_str_asc))

    desde_str = st.sidebar.selectbox("Desde", fechas_str_asc, index=0)
    hasta_str = st.sidebar.selectbox("Hasta", fechas_str_desc, index=0)
    desde = pd.to_datetime(desde_str)
    hasta = pd.to_datetime(hasta_str)

    if hasta < desde:
        desde, hasta = hasta, desde

    indice_a = base.loc[base["fecha"] == desde, "indice"]
    indice_b = base.loc[base["fecha"] == hasta, "indice"]

    if indice_a.empty or indice_b.empty:
        st.warning("No se encontraron índices para las fechas seleccionadas.")
    else:
        valor_a = indice_a.iloc[0]
        valor_b = indice_b.iloc[0]
        inflacion_acum = (valor_b / valor_a - 1) * 100

        st.subheader("📈 Cálculo de inflación acumulada")
        st.write(f"**Período:** {desde_str} → {hasta_str}")
        st.write(f"**Índice inicial:** {valor_a:.3f}")
        st.write(f"**Índice final:** {valor_b:.3f}")
        st.write(f"**Inflación acumulada:** {inflacion_acum:.2f} %")

        monto = st.number_input("💰 Ingresá un monto en pesos del período inicial", min_value=0.0, value=0.0, step=100.0)
        monto_final = st.number_input("💰 Ingresá un monto en pesos del período final (opcional)", min_value=0.0, value=0.0, step=100.0)

        if monto > 0:
            monto_actualizado = monto * (valor_b / valor_a)
            st.write("---")
            st.subheader("💵 Actualización de monto según IPC")
            st.write(f"Monto original ({desde_str}): **${monto:,.2f}**")
            st.write(f"Monto actualizado ({hasta_str}): **${monto_actualizado:,.2f}**")

            # Si hay monto final, calcular diferencia real
            if monto_final > 0:
                diferencia_pesos = monto_final - monto_actualizado
                diferencia_pct = (monto_final / monto_actualizado - 1) * 100
                resultado = "Ganancia real" if diferencia_pesos > 0 else "Pérdida real"
                color = "green" if diferencia_pesos > 0 else "red"
                st.write("---")
                st.markdown(
                    f"<h4 style='color:{color}'>📊 {resultado}: ${diferencia_pesos:,.2f} ({diferencia_pct:+.2f} %)</h4>",
                    unsafe_allow_html=True
                )

        # --- Cálculo de variación acumulada para cada punto ---
        datos = base[(base["fecha"] >= desde) & (base["fecha"] <= hasta)].copy()
        datos["variacion_acum"] = (datos["indice"] / valor_a - 1) * 100

        fig = px.line(
            datos,
            x="fecha",
            y="indice",
            markers=True,
            title=f"Evolución del índice – {categoria} en {region} ({origen})"
        )

        # Etiquetas de porcentaje acumulado sobre cada punto
        fig.update_traces(
            text=[f"{v:.1f}%" for v in datos["variacion_acum"]],
            textposition="top center",
            textfont=dict(size=12, color="black"),
            mode="lines+markers+text"
        )

        st.plotly_chart(fig, use_container_width=True, key="acumulado")

