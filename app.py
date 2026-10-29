
import hashlib
import math
import time
from datetime import datetime

import streamlit as st
import plotly.express as px
import pandas as pd

from base_datos import database as db
from config import (CORRELACION, ESTADOS_ALERTA, ESTADOS_INCIDENTE, GENERADOR,
                    MAX_EVENTOS_GRAFICAS, RUTA_CSV, SEVERIDADES)
from generador.eventos import GeneradorEventos
from interfaz import graficas
from interfaz.tema import (
    VERDE_FIME, VERDE_FONDO, VERDE_TARJETA, ROJO_ANOMALIA, AZUL_NORMAL,
    GRIS_GENERAL, GRIS_CLARO, AMARILLO_GRAFICA, BLANCO
)
from servicios import deteccion
from servicios.correlacion import correlacionar
from servicios.exportacion import COLUMNAS_ALERTAS, COLUMNAS_EVENTOS, a_csv
from servicios.kpi import calcular_kpis

# ==================================================
# CONFIGURACIÓN GENERAL
# ==================================================

st.set_page_config(
    page_title="CyberRadar FIME | SOC Dashboard",
    layout="wide"
)

# ==================================================
# Nuestro diseño CSS
# ==================================================

st.markdown("""
<style>
.stApp {
    background-color: #10251A;
    color: #F9FAFB;
}

[data-testid="stHeader"] {
    background-color: #10251A;
}

[data-testid="stSidebar"] {
    background-color: #183B2A;
}

.block-container {
    padding-top: 2rem;
    padding-bottom: 2rem;
}

h1, h2, h3 {
    color: #FACC15 !important;
}

p, label, .stMarkdown {
    color: #D1D5DB;
}

[data-testid="stMetric"] {
    background-color: #183B2A;
    border: 1px solid #6B7280;
    padding: 20px;
    border-radius: 12px;
}

[data-testid="stMetricLabel"] {
    color: #D1D5DB;
}

[data-testid="stMetricValue"] {
    color: #FACC15;
}

div[data-testid="stDataFrame"] {
    border: 1px solid #6B7280;
    border-radius: 10px;
}

.stButton button,
.stDownloadButton button,
[data-testid="stFormSubmitButton"] button {
    background-color: #14532D;
    color: #F9FAFB;
    border: 1px solid #6B7280;
    border-radius: 8px;
}

.stButton button:hover,
.stDownloadButton button:hover,
[data-testid="stFormSubmitButton"] button:hover {
    background-color: #166534;
    color: #FFFFFF;
    border-color: #FACC15;
}

hr {
    border-color: #6B7280;
}

button[data-baseweb="tab"] {
    color: #D1D5DB;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #FACC15;
}

[data-testid="stExpander"] {
    border: 1px solid #6B7280;
    border-radius: 10px;
}

</style>
""", unsafe_allow_html=True)

# ==================================================
# ENCABEZADO
# ==================================================

st.title(" CyberRadar FIME")

st.caption(
    "NETWORK SECURITY MONITORING | "
    "INTELLIGENT ANOMALY DETECTION"
)

st.divider()

# ==================================================
# Estado y recursos
# ==================================================

ss = st.session_state
ss.setdefault("sim_activa", False)
ss.setdefault("ultimo_ciclo", 0.0)
ss.setdefault("ultima_actualizacion", None)
if "generador" not in ss:
    ss.generador = GeneradorEventos()

db.inicializar_base_datos()


@st.cache_resource
def detector_simulacion():
    return deteccion.entrenar_detector_simulacion()


def pausar():
    ss.sim_activa = False


def iniciar():
    ss.sim_activa = True


def mostrar_aviso():
    if ss.get("aviso"):
        st.success(ss.pop("aviso"))


# ==================================================
# Modo y controles
# ==================================================

col_modo, col_ini, col_pau = st.columns([3, 1, 1])

with col_modo:
    modo_ui = st.radio(
        "Modo de análisis",
        ["Simulación autónoma", "Análisis de CSV"],
        horizontal=True,
        key="modo_ui",
        on_change=pausar
    )

modo = "simulacion" if modo_ui == "Simulación autónoma" else "csv"
es_sim = modo == "simulacion"

with col_ini:
    st.write("")
    st.button("Iniciar simulación", on_click=iniciar, width="stretch",
              disabled=(not es_sim) or ss.sim_activa)

with col_pau:
    st.write("")
    st.button("Pausar simulación", on_click=pausar, width="stretch",
              disabled=(not es_sim) or (not ss.sim_activa))

with st.sidebar:
    if es_sim:
        st.subheader("Parámetros de la simulación")
        intervalo = st.slider("Intervalo (segundos)", 1, 10, int(GENERADOR["intervalo_s"]))
        por_ciclo = st.slider("Eventos por ciclo", 1, 20, GENERADOR["eventos_por_ciclo"])
        atipicos = st.slider("Eventos atípicos (%)", 0, 30,
                             round(GENERADOR["proporcion_atipica"] * 100))
        ss.generador.configurar(intervalo, por_ciclo, atipicos / 100)
        subido = None
    else:
        st.subheader("Archivo CSV")
        subido = st.file_uploader("CSV propio (opcional)", type=["csv"])

# ==================================================
# Origen de los datos
# ==================================================

fuente_csv = None
if not es_sim:
    try:
        if subido is not None:
            contenido, nombre = subido.getvalue(), subido.name
        else:
            contenido, nombre = RUTA_CSV.read_bytes(), RUTA_CSV.name
        clave = hashlib.sha1(contenido).hexdigest()
        if ss.get("csv_clave") != clave:
            ss.csv_fuente, ss.csv_res = deteccion.analizar_csv(contenido, nombre)
            ss.csv_clave = clave
            ss.ultima_actualizacion = datetime.now()
    except (ValueError, FileNotFoundError) as error:
        st.error(str(error))
        st.stop()
    fuente_csv = ss.csv_fuente


def ciclo_simulacion():
    gen = ss.generador
    if time.time() - ss.ultimo_ciclo < 0.8 * gen.intervalo_s:
        return
    ss.ultimo_ciclo = time.time()
    deteccion.procesar_eventos(gen.generar_ciclo(), detector_simulacion(), "simulacion", "generador")
    ss.ultima_actualizacion = datetime.now()


intervalo_ref = ss.generador.intervalo_s if (es_sim and ss.sim_activa) else None


# ==================================================
# Estado del sistema (se actualiza solo)
# ==================================================

def estado_sistema():
    if es_sim and ss.sim_activa:
        ciclo_simulacion()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Modo activo", "Simulación sintética" if es_sim else "Análisis de CSV")
    if es_sim:
        c2.metric("Simulación", "Activa" if ss.sim_activa else "En pausa")
    else:
        c2.metric("Simulación", "No aplica")
    c3.metric("Motor de detección", "Isolation Forest listo")
    ultima = ss.ultima_actualizacion
    c4.metric("Última actualización", ultima.strftime("%H:%M:%S") if ultima else "—")


st.fragment(estado_sistema, run_every=intervalo_ref)()

st.divider()

# ==================================================
# Panel de monitoreo (se actualiza solo)
# ==================================================

def panel_monitoreo():
    ind = db.indicadores(modo, fuente_csv)
    datos = db.cargar_eventos(modo, fuente_csv, MAX_EVENTOS_GRAFICAS)
    kpi = calcular_kpis(ind, datos["fecha"] if not datos.empty else [],
                        datetime.now() if es_sim else None)

    if not es_sim:
        rechazados = ss.csv_res.rechazados
        if len(rechazados):
            st.warning(f"{len(rechazados)} fila(s) rechazadas por datos no válidos.")
            with st.expander("Ver filas rechazadas"):
                st.dataframe(rechazados, hide_index=True)

    # ==================================================
    # Indicadores de seguridad
    # ==================================================

    st.subheader("Resumen de seguridad")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Conexiones analizadas",
        f"{kpi['eventos']:,}"
    )

    col2.metric(
        "Anomalías detectadas",
        f"{kpi['anomalias']:,}",
        delta=f"{kpi['pct_anomalo']:.1f}% del tráfico",
        delta_color="inverse"
    )

    col3.metric(
        "Tráfico normal",
        f"{kpi['pct_normal']:.1f}%"
    )

    col4.metric(
        "Porcentaje anómalo",
        f"{kpi['pct_anomalo']:.1f}%"
    )

    col5, col6, col7 = st.columns(3)

    col5.metric("Alertas pendientes de revisión", f"{kpi['pendientes']:,}")
    col6.metric("Incidentes abiertos", f"{kpi['incidentes_abiertos']:,}")
    col7.metric(
        "Eventos por minuto",
        "N/D" if kpi["eventos_min"] is None else f"{kpi['eventos_min']:.1f}"
    )

    if datos.empty:
        st.info("Sin eventos.")
        return

    st.divider()

    # ==================================================
    # graficas
    # ==================================================

    st.subheader("Análisis del tráfico de red")

    col_grafica1, col_grafica2 = st.columns(2)

    # --------------------------------------------------
    # grafica uno
    # --------------------------------------------------

    with col_grafica1:

        conteo = pd.DataFrame({
            "Estado": ["Normal", "Anomalía"],
            "Cantidad": [kpi["normales"], kpi["anomalias"]]
        })

        fig_pastel = px.pie(
            conteo,
            names="Estado",
            values="Cantidad",
            title="Distribución del tráfico",
            hole=0.55,
            color="Estado",
            color_discrete_map={
                "Normal": AZUL_NORMAL,
                "Anomalía": ROJO_ANOMALIA
            }
        )

        fig_pastel.update_traces(
            textposition="inside",
            textinfo="percent+label",
            marker_line_color=VERDE_FONDO,
            marker_line_width=2
        )

        fig_pastel.update_layout(
            template="plotly_dark",
            paper_bgcolor=VERDE_FONDO,
            plot_bgcolor=VERDE_FONDO,
            font_color=BLANCO,
            title_font_color=AMARILLO_GRAFICA,
            legend_title_text="Clasificación",
            margin=dict(t=60, b=20, l=20, r=20)
        )

        st.plotly_chart(fig_pastel, width="stretch")

    with col_grafica2:

        columnas_necesarias = {
            "bytes",
            "paquetes",
            "estado"
        }

        if columnas_necesarias.issubset(datos.columns):

            fig_trafico = px.scatter(
                datos,
                x="bytes",
                y="paquetes",
                color="estado",
                title="Relación entre bytes y paquetes",
                color_discrete_map={
                    "Normal": AZUL_NORMAL,
                    "Anomalía": ROJO_ANOMALIA
                },
                hover_data=[
                    c for c in [
                        "duracion",
                        "puertos",
                        "anomaly_score"
                    ]
                    if c in datos.columns
                ],
                labels={
                    "bytes": "Bytes transferidos",
                    "paquetes": "Cantidad de paquetes",
                    "estado": "Clasificación"
                }
            )

            fig_trafico.update_traces(
                marker=dict(
                    size=10,
                    line=dict(
                        width=1,
                        color=GRIS_GENERAL
                    )
                )
            )

            fig_trafico.update_layout(
                template="plotly_dark",
                paper_bgcolor=VERDE_FONDO,
                plot_bgcolor=VERDE_FONDO,
                font_color=BLANCO,
                title_font_color=AMARILLO_GRAFICA,
                xaxis=dict(
                    title_font_color=AMARILLO_GRAFICA,
                    gridcolor=GRIS_GENERAL
                ),
                yaxis=dict(
                    title_font_color=AMARILLO_GRAFICA,
                    gridcolor=GRIS_GENERAL
                ),
                margin=dict(t=60, b=20, l=20, r=20)
            )

            st.plotly_chart(fig_trafico, width="stretch")

        else:
            st.info("Sin datos.")

    # --------------------------------------------------
    # Gráficas nuevas
    # --------------------------------------------------

    tiene_tiempo = datos["fecha"].notna().any()

    def mostrar(figura, vacio):
        if figura is None:
            st.info(vacio)
        else:
            st.plotly_chart(figura, width="stretch")

    sin_hora = "Sin marcas de tiempo."

    g1, g2 = st.columns(2)
    with g1:
        mostrar(graficas.actividad_tiempo(datos) if tiene_tiempo
                else graficas.actividad_registro(datos), sin_hora)
    with g2:
        mostrar(graficas.anomalias_intervalo(datos) if tiene_tiempo else None, sin_hora)

    g3, g4 = st.columns(2)
    with g3:
        mostrar(graficas.evolucion_anomalias(datos) if tiene_tiempo else None,
                sin_hora if not tiene_tiempo else "Todavía no hay anomalías.")
    with g4:
        mostrar(graficas.puertos(datos), "No hay datos de puertos.")

    g5, g6 = st.columns(2)
    with g5:
        mostrar(graficas.top_ips(datos, "ip_origen", "Principales IP de origen"),
                "No hay IP de origen.")
    with g6:
        mostrar(graficas.top_ips(datos, "ip_destino", "Principales IP de destino"),
                "No hay IP de destino.")

    st.divider()

    # ==================================================
    # Puntiacion de las anomalias basadas en isolation forest
    # ==================================================

    st.subheader("Puntuación del modelo")

    if "anomaly_score" in datos.columns:

        datos_score = datos.tail(300).copy()

        datos_score["Clasificación"] = datos_score["estado"]

        fig_score = px.bar(
            datos_score,
            x=datos_score.index.astype(str),
            y="anomaly_score",
            color="Clasificación",
            title="Puntuación de anomalía por registro",
            color_discrete_map={
                "Normal": AZUL_NORMAL,
                "Anomalía": ROJO_ANOMALIA
            },
            labels={
                "x": "Registro",
                "anomaly_score": "Puntuación del modelo",
                "Clasificación": "Clasificación"
            },
            hover_data=[
                c for c in [
                    "bytes",
                    "paquetes",
                    "duracion",
                    "puertos"
                ]
                if c in datos_score.columns
            ]
        )

        fig_score.update_layout(
            template="plotly_dark",
            paper_bgcolor=VERDE_FONDO,
            plot_bgcolor=VERDE_FONDO,
            font_color=BLANCO,
            title_font_color=AMARILLO_GRAFICA,
            xaxis=dict(
                title="Registro",
                title_font_color=AMARILLO_GRAFICA,
                gridcolor=GRIS_GENERAL
            ),
            yaxis=dict(
                title="Puntuación del modelo",
                title_font_color=AMARILLO_GRAFICA,
                gridcolor=GRIS_GENERAL
            ),
            showlegend=True,
            margin=dict(t=60, b=40, l=20, r=20)
        )

        st.plotly_chart(fig_score, width="stretch")

    else:
        st.info("Sin puntuación.")

    st.divider()

    # ==================================================
    # trafico
    # ==================================================

    st.subheader("Trafico analizado")

    opciones_filtro = [
        "Todas",
        "Anomalía",
        "Normal"
    ]

    f1, f2, f3 = st.columns(3)

    with f1:
        filtro = st.selectbox(
            "Filtrar conexiones por clasificación",
            opciones_filtro,
            key="f_estado"
        )
    with f2:
        sev_sel = st.multiselect("Severidad", SEVERIDADES, key="f_sev")
    with f3:
        ip_buscar = st.text_input("Buscar IP", key="f_ip").strip()

    datos_filtrados = datos.iloc[::-1]

    if filtro != "Todas":
        datos_filtrados = datos_filtrados[
            datos_filtrados["estado"] == filtro
        ]
    if sev_sel:
        datos_filtrados = datos_filtrados[datos_filtrados["severidad"].isin(sev_sel)]
    if ip_buscar:
        datos_filtrados = datos_filtrados[
            datos_filtrados["ip_origen"].fillna("").str.contains(ip_buscar, regex=False)
            | datos_filtrados["ip_destino"].fillna("").str.contains(ip_buscar, regex=False)
        ]

    st.write(
        f"Conexiones mostradas: {len(datos_filtrados)}"
    )

    p1, p2, p3 = st.columns([1, 1, 2])
    with p1:
        tamano = st.selectbox("Filas por página", [25, 50, 100], key="f_tam")
    paginas = max(1, math.ceil(len(datos_filtrados) / tamano))
    with p2:
        pagina = st.number_input("Página", 1, paginas, 1, key="f_pag")
    with p3:
        con_escenario = st.checkbox("Mostrar escenario", key="f_esc",
                                    disabled=not es_sim)

    columnas_tabla = COLUMNAS_EVENTOS + (["escenario"] if con_escenario else [])
    inicio = (pagina - 1) * tamano

    st.dataframe(
        datos_filtrados[[c for c in columnas_tabla if c in datos_filtrados]].iloc[inicio:inicio + tamano],
        hide_index=True
    )

    csv_trafico = a_csv(datos_filtrados, columnas_tabla)

    st.download_button(
        label="Descargar tráfico filtrado CSV",
        data=csv_trafico,
        file_name="trafico_analizado.csv",
        mime="text/csv"
    )


# ==================================================
# Alertas
# ==================================================

def etiqueta_alerta(f):
    return f"ALR-{f['id']:05d} · {f['severidad']} · {f['estado_revision']}"


def detalle_alerta(alerta_id):
    a = db.obtener_alerta(alerta_id)
    st.subheader(f"Detalle de la alerta ALR-{a['id']:05d}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Severidad estimada", a["severidad"] or "—")
    c2.metric("Estado de revisión", a["estado_revision"])
    c3.metric("Puntuación", f"{a['anomaly_score']:.3f}")
    c4.metric("Origen", "Simulación" if a["modo"] == "simulacion" else "CSV")

    st.write(f"**Motivo de detección:** {a['regla'] or 'Alerta del esquema anterior, sin regla registrada.'}")
    if a["motivo_cierre"]:
        st.write(f"**Motivo de cierre:** {a['motivo_cierre']}")

    resumen = {
        "Fecha": a["fecha"], "IP origen": a["ip_origen"] or "—", "IP destino": a["ip_destino"] or "—",
        "Puerto destino": a["puerto_destino"] if a["puerto_destino"] is not None else "—",
        "Protocolo": a["protocolo"] or "—", "Evento original": a["evento_id"],
    }
    st.dataframe(pd.DataFrame([resumen]).astype(str), hide_index=True)

    # Contexto descriptivo frente a los eventos observados
    ref = db.cargar_eventos(a["modo"], a["fuente"] if a["modo"] == "csv" else None, 2000)
    if not ref.empty:
        filas = []
        for c in ["bytes", "paquetes", "duracion", "puertos"]:
            mediana = float(ref[c].median())
            filas.append({"Característica": c, "Valor": a[c], "Mediana observada": mediana,
                          "Veces la mediana": round(a[c] / mediana, 1) if mediana else None})
        st.write("**Características frente a la mediana**")
        st.dataframe(pd.DataFrame(filas), hide_index=True)

    # Contexto temporal y eventos relacionados
    ev = db.obtener_evento(a["evento_id"])
    if ev and ev["fecha"] and ev["ip_origen"]:
        centro = pd.Timestamp(ev["fecha"])
        v = pd.Timedelta(seconds=CORRELACION["ventana_s"])
        formato = "%Y-%m-%d %H:%M:%S.%f"
        rel = db.eventos_en_ventana(a["modo"], (centro - v).strftime(formato)[:-3],
                                    (centro + v).strftime(formato)[:-3], ev["ip_origen"])
        n_anom = int((rel["estado"] == "Anomalía").sum()) if not rel.empty else 0
        st.write(f"**Eventos relacionados:** {len(rel)} del mismo origen "
                 f"en ±{CORRELACION['ventana_s']} s ({n_anom} anómalos)")
        if not rel.empty:
            st.dataframe(rel[["fecha", "ip_destino", "puerto_destino", "bytes", "paquetes",
                              "duracion", "puertos", "estado", "anomaly_score", "severidad"]],
                         hide_index=True)
    else:
        st.caption("Sin marcas de tiempo.")

    # Estado
    st.write("**Revisión**")
    with st.form(f"estado_{a['id']}"):
        nuevo = st.selectbox("Estado", ESTADOS_ALERTA, index=ESTADOS_ALERTA.index(a["estado_revision"]))
        motivo = st.text_input("Motivo")
        if st.form_submit_button("Actualizar estado"):
            try:
                if db.cambiar_estado_alerta(a["id"], nuevo, motivo):
                    ss.aviso = "Estado actualizado."
                    st.rerun()
                st.info("El estado ya era ese.")
            except ValueError as error:
                st.error(str(error))

    # Notas
    st.write("**Notas del analista**")
    notas = db.obtener_notas(alerta_id=a["id"])
    if notas.empty:
        st.caption("Sin notas.")
    else:
        st.dataframe(notas.rename(columns={"fecha": "Fecha", "texto": "Nota"})[["Fecha", "Nota"]],
                     hide_index=True)
    with st.form(f"nota_{a['id']}", clear_on_submit=True):
        texto = st.text_area("Nueva nota", max_chars=2000)
        if st.form_submit_button("Guardar nota"):
            try:
                db.agregar_nota(texto, alerta_id=a["id"])
                ss.aviso = "Nota guardada."
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    # Historial
    st.write("**Historial de cambios**")
    st.dataframe(db.obtener_historial("alerta", a["id"]).rename(columns={
        "fecha": "Fecha", "anterior": "Antes", "nuevo": "Ahora", "motivo": "Motivo"}),
        hide_index=True)

    # Incidente
    st.write("**Incidente**")
    if a["incidente_id"]:
        st.write(f"Esta alerta pertenece al incidente INC-{a['incidente_id']:04d}.")
    else:
        with st.form(f"incidente_{a['id']}"):
            titulo = st.text_input("Título del incidente",
                                   value=f"Actividad atípica de {a['ip_origen'] or 'origen desconocido'}")
            if st.form_submit_button("Crear incidente desde esta alerta"):
                try:
                    iid = db.crear_incidente(titulo, [a["id"]], criterio="Creado por el analista")
                    ss.aviso = f"Incidente INC-{iid:04d} creado."
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
        abiertos = db.listar_incidentes(a["modo"], ["Abierto", "En investigación"])
        if not abiertos.empty:
            with st.form(f"anadir_{a['id']}"):
                destino = st.selectbox("Añadir a un incidente abierto", abiertos["id"].tolist(),
                                       format_func=lambda i: f"INC-{i:04d}")
                if st.form_submit_button("Añadir alerta"):
                    try:
                        db.agregar_alertas_a_incidente(destino, [a["id"]])
                        ss.aviso = f"Alerta añadida a INC-{destino:04d}."
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))



def vista_alertas():
    mostrar_aviso()

    # ==================================================
    # HISTORIAL PERSISTENTE DE ALERTAS
    # ==================================================

    st.subheader(" Historial de alertas")

    origenes = {"Simulación": "simulacion", "CSV": "csv", "Todos": None}
    a1, a2, a3 = st.columns(3)
    with a1:
        origen = st.selectbox("Origen", list(origenes), index=0 if es_sim else 1,
                              key=f"fa_origen_{modo}")
    with a2:
        sevs = st.multiselect("Severidad", SEVERIDADES, key="fa_sev")
    with a3:
        estados = st.multiselect("Estado de revisión", ESTADOS_ALERTA, key="fa_est")
    b1, b2, b3 = st.columns(3)
    with b1:
        desde = st.date_input("Desde", value=None, key="fa_desde")
    with b2:
        hasta = st.date_input("Hasta", value=None, key="fa_hasta")
    with b3:
        ip = st.text_input("IP (origen o destino)", key="fa_ip").strip()

    filtros = dict(modo=origenes[origen], severidades=sevs, estados=estados,
                   desde=desde, hasta=hasta, ip=ip)
    total = db.contar_alertas(filtros)

    st.metric(
        "Alertas históricas registradas",
        total
    )

    if total == 0:
        st.info("Sin alertas.")
        return

    q1, q2 = st.columns(2)
    with q1:
        tamano = st.selectbox("Alertas por página", [25, 50, 100], key="fa_tam")
    paginas = max(1, math.ceil(total / tamano))
    with q2:
        pagina = st.number_input("Página de alertas", 1, paginas, 1, key="fa_pag")

    df = db.consultar_alertas(filtros, tamano, (pagina - 1) * tamano)
    vista = df.drop(columns=["regla", "evento_id", "fuente"]).rename(columns={
        "modo": "origen", "estado_revision": "estado"})
    st.dataframe(vista, hide_index=True)

    st.download_button(
        label="Descargar historial de alertas CSV",
        data=a_csv(db.consultar_alertas(filtros, 10000), COLUMNAS_ALERTAS),
        file_name="historial_alertas.csv",
        mime="text/csv"
    )

    st.divider()
    etiquetas = {int(f["id"]): etiqueta_alerta(f) for f in df.to_dict("records")}
    elegida = st.selectbox("Alerta a investigar", list(etiquetas), format_func=etiquetas.get)
    detalle_alerta(elegida)


# ==================================================
# Incidentes y correlación
# ==================================================

def propuestas_correlacion():
    st.subheader("Correlación de eventos")
    eventos = db.cargar_eventos(modo, fuente_csv, MAX_EVENTOS_GRAFICAS)
    if eventos.empty or not eventos["fecha"].notna().any():
        st.info("Sin marcas de tiempo.")
        return
    grupos = correlacionar(eventos)
    if not grupos:
        st.info("Sin grupos.")
        return
    for g in grupos[:15]:
        titulo = (f"{g['regla']} · {g['clave']} · {g['severidad']} · "
                  f"{g['n_anomalias']} anomalías")
        with st.expander(titulo):
            st.write(g["explicacion"])
            st.write(f"Del {g['inicio']} al {g['fin']} · {g['n_eventos']} eventos")
            sin_inc = [a for a in g["alerta_ids"]
                       if eventos.loc[eventos["alerta_id"] == a, "incidente_id"].isna().all()]
            if g["incidente_ids"]:
                destino = g["incidente_ids"][0]
                st.write(f"Ya registrado en INC-{destino:04d}.")
                if sin_inc and st.button(f"Añadir {len(sin_inc)} alerta(s) nueva(s) a INC-{destino:04d}",
                                         key=f"add_{g['id']}"):
                    try:
                        db.agregar_alertas_a_incidente(destino, sin_inc)
                        ss.aviso = "Alertas añadidas al incidente."
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
            else:
                titulo_inc = st.text_input("Título del incidente", key=f"tit_{g['id']}",
                                           value=f"{g['regla']}: {g['clave']}")
                if st.button("Crear incidente", key=f"crear_{g['id']}"):
                    try:
                        iid = db.crear_incidente(titulo_inc, g["alerta_ids"], g["explicacion"],
                                                 f"Correlación: {g['regla']}")
                        ss.aviso = f"Incidente INC-{iid:04d} creado."
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))


def detalle_incidente(incidente_id):
    i = db.obtener_incidente(incidente_id)
    st.subheader(f"Detalle del incidente INC-{i['id']:04d}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Severidad", i["severidad"])
    c2.metric("Estado", i["estado"])
    c3.metric("Origen", "Simulación" if i["modo"] == "simulacion" else "CSV")
    c4.metric("Creado", i["creado"][:16])
    st.write(f"**{i['titulo']}**")
    if i["resumen"]:
        st.write(i["resumen"])
    st.write(f"**Criterio:** {i['criterio']}")
    if i["motivo_cierre"]:
        st.write(f"**Motivo de cierre:** {i['motivo_cierre']}")

    st.write("**Alertas relacionadas**")
    alertas = db.consultar_alertas(dict(incidente_id=i["id"]), 500)
    st.dataframe(alertas.drop(columns=["regla", "evento_id", "fuente", "modo"]), hide_index=True)
    st.download_button("Descargar alertas del incidente CSV", a_csv(alertas, COLUMNAS_ALERTAS),
                       file_name=f"incidente_{i['id']:04d}_alertas.csv", mime="text/csv",
                       key=f"dl_inc_{i['id']}")

    eventos = db.eventos_de_incidente(i["id"])
    if not eventos.empty:
        st.write("**Cronología de eventos**")
        st.dataframe(eventos[["fecha", "ip_origen", "ip_destino", "puerto_destino", "bytes",
                              "paquetes", "duracion", "puertos", "anomaly_score", "severidad"]],
                     hide_index=True)

    st.write("**Estado del incidente**")
    with st.form(f"estado_inc_{i['id']}"):
        nuevo = st.selectbox("Estado", ESTADOS_INCIDENTE, index=ESTADOS_INCIDENTE.index(i["estado"]))
        motivo = st.text_input("Motivo")
        if st.form_submit_button("Actualizar incidente"):
            try:
                if db.cambiar_estado_incidente(i["id"], nuevo, motivo):
                    ss.aviso = "Incidente actualizado."
                    st.rerun()
                st.info("El estado ya era ese.")
            except ValueError as error:
                st.error(str(error))

    st.write("**Notas del incidente**")
    notas = db.obtener_notas(incidente_id=i["id"])
    if notas.empty:
        st.caption("Sin notas.")
    else:
        st.dataframe(notas.rename(columns={"fecha": "Fecha", "texto": "Nota"})[["Fecha", "Nota"]],
                     hide_index=True)
    with st.form(f"nota_inc_{i['id']}", clear_on_submit=True):
        texto = st.text_area("Nueva nota del incidente", max_chars=2000)
        if st.form_submit_button("Guardar nota del incidente"):
            try:
                db.agregar_nota(texto, incidente_id=i["id"])
                ss.aviso = "Nota guardada."
                st.rerun()
            except ValueError as error:
                st.error(str(error))

    st.write("**Historial de cambios**")
    st.dataframe(db.obtener_historial("incidente", i["id"]).rename(columns={
        "fecha": "Fecha", "anterior": "Antes", "nuevo": "Ahora", "motivo": "Motivo"}),
        hide_index=True)


def vista_incidentes():
    mostrar_aviso()
    propuestas_correlacion()
    st.divider()
    st.subheader("Incidentes")
    estados = st.multiselect("Estado", ESTADOS_INCIDENTE, key="fi_est")
    lista = db.listar_incidentes(modo, estados or None, 100)
    if lista.empty:
        st.info("Sin incidentes.")
        return
    st.dataframe(lista.drop(columns=["modo"]), hide_index=True)
    etiquetas = {int(f["id"]): f"INC-{f['id']:04d} · {f['severidad']} · {f['estado']}"
                 for f in lista.to_dict("records")}
    elegido = st.selectbox("Incidente a investigar", list(etiquetas), format_func=etiquetas.get)
    detalle_incidente(elegido)


# ==================================================
# Pantallas
# ==================================================

tab_mon, tab_alertas, tab_inc = st.tabs(["Monitoreo", "Alertas", "Incidentes"])

with tab_mon:
    st.fragment(panel_monitoreo, run_every=intervalo_ref)()

with tab_alertas:
    vista_alertas()

with tab_inc:
    vista_incidentes()

st.divider()

st.caption(
    "CyberRadar FIME | Network Anomaly Detector"
)
