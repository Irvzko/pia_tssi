import pandas as pd
import plotly.express as px

from interfaz.tema import (AMARILLO_GRAFICA, BLANCO, COLORES_ESTADO, GRIS_GENERAL,
                           ROJO_ANOMALIA, VERDE_FONDO)

ORDEN_ESTADO = {"estado": ["Normal", "Anomalía"]}


def _tema(fig, x=None, y=None, altura=320):
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=VERDE_FONDO, plot_bgcolor=VERDE_FONDO,
        font_color=BLANCO, title_font_color=AMARILLO_GRAFICA, height=altura,
        xaxis=dict(title=x, title_font_color=AMARILLO_GRAFICA, gridcolor=GRIS_GENERAL),
        yaxis=dict(title=y, title_font_color=AMARILLO_GRAFICA, gridcolor=GRIS_GENERAL),
        legend_title_text="Clasificación", margin=dict(t=60, b=30, l=20, r=20),
    )
    return fig


def _frecuencia(t):
    seg = max((t.max() - t.min()).total_seconds(), 1)
    for f, s in (("10s", 10), ("30s", 30), ("1min", 60), ("5min", 300), ("15min", 900), ("1h", 3600)):
        if seg / s <= 40:
            return f
    return "6h"


def _por_intervalo(datos):
    t = pd.to_datetime(datos["fecha"], errors="coerce")
    d = datos.assign(_t=t).dropna(subset=["_t"])
    if d.empty:
        return None, None
    f = _frecuencia(d["_t"])
    tabla = (d.groupby([pd.Grouper(key="_t", freq=f), "estado"]).size()
             .unstack(fill_value=0).reindex(columns=["Normal", "Anomalía"], fill_value=0))
    tabla = tabla.asfreq(f, fill_value=0)
    return tabla, f


def actividad_tiempo(datos):
    tabla, f = _por_intervalo(datos)
    if tabla is None:
        return None
    df = pd.DataFrame({"Intervalo": tabla.index, "Eventos": tabla.sum(axis=1).values,
                       "Anomalías": tabla["Anomalía"].values})
    fig = px.line(df, x="Intervalo", y=["Eventos", "Anomalías"],
                  title=f"Actividad de red (por {f})",
                  color_discrete_map={"Eventos": AMARILLO_GRAFICA, "Anomalías": ROJO_ANOMALIA})
    fig.update_layout(legend_title_text="Serie")
    return _tema(fig, "Hora", "Eventos")


def anomalias_intervalo(datos):
    tabla, f = _por_intervalo(datos)
    if tabla is None:
        return None
    df = pd.DataFrame({"Intervalo": tabla.index, "Anomalías": tabla["Anomalía"].values})
    fig = px.bar(df, x="Intervalo", y="Anomalías", title=f"Anomalías por intervalo ({f})",
                 color_discrete_sequence=[ROJO_ANOMALIA])
    return _tema(fig, "Hora", "Anomalías")


def evolucion_anomalias(datos):
    t = pd.to_datetime(datos["fecha"], errors="coerce")
    d = datos.assign(_t=t).dropna(subset=["_t"]).sort_values("_t")
    d = d[d["estado"] == "Anomalía"]
    if d.empty:
        return None
    d = d.assign(Acumuladas=range(1, len(d) + 1))
    fig = px.line(d, x="_t", y="Acumuladas", title="Evolución de anomalías (acumuladas)",
                  color_discrete_sequence=[AMARILLO_GRAFICA])
    return _tema(fig, "Hora", "Anomalías acumuladas")


def puertos(datos):
    if "puerto_destino" in datos and datos["puerto_destino"].notna().any():
        d = datos.dropna(subset=["puerto_destino"]).copy()
        d["Puerto"] = d["puerto_destino"].astype(int).astype(str)
        top = d["Puerto"].value_counts().head(10).index
        tabla = d[d["Puerto"].isin(top)].groupby(["Puerto", "estado"]).size().reset_index(name="Eventos")
        fig = px.bar(tabla, x="Puerto", y="Eventos", color="estado", title="Puertos de destino observados",
                     color_discrete_map=COLORES_ESTADO, category_orders={"Puerto": list(top), **ORDEN_ESTADO})
        return _tema(fig, "Puerto", "Eventos")
    tabla = datos.groupby(["puertos", "estado"]).size().reset_index(name="Eventos")
    fig = px.bar(tabla, x="puertos", y="Eventos", color="estado",
                 title="Puertos distintos por conexión", color_discrete_map=COLORES_ESTADO,
                 category_orders=ORDEN_ESTADO)
    return _tema(fig, "Puertos distintos", "Conexiones")


def top_ips(datos, columna, titulo):
    if columna not in datos or datos[columna].dropna().empty:
        return None
    top = datos[columna].value_counts().head(8).index
    tabla = (datos[datos[columna].isin(top)].groupby([columna, "estado"]).size()
             .reset_index(name="Eventos"))
    fig = px.bar(tabla, x="Eventos", y=columna, color="estado", orientation="h", title=titulo,
                 color_discrete_map=COLORES_ESTADO,
                 category_orders={columna: list(top)[::-1], **ORDEN_ESTADO})
    return _tema(fig, "Eventos", None)


def actividad_registro(datos):
    d = datos.reset_index(drop=True).assign(Registro=lambda x: x.index + 1)
    fig = px.bar(d, x="Registro", y="bytes", color="estado", title="Actividad de red por registro",
                 color_discrete_map=COLORES_ESTADO, category_orders=ORDEN_ESTADO)
    fig.update_yaxes(type="log")
    return _tema(fig, "Registro", "Bytes (escala log)")
