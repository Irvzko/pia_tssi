import hashlib
from dataclasses import dataclass, field

import pandas as pd

from base_datos import database as db
from config import (CARACTERISTICAS, CONTEXTO_RAZON, MODELO_CSV, MODELO_SIM, REFERENCIA_N,
                    REFERENCIA_SEMILLA, EVALUACION_N, EVALUACION_SEMILLA,
                    severidad_por_puntuacion)
from generador.eventos import generar_evaluacion, generar_referencia_normal
from modelo.isolation_forest import DetectorAnomalias, evaluar_detector
from servicios.validacion import leer_csv, validar_eventos


@dataclass
class Resultado:
    eventos: int = 0
    anomalias: int = 0
    alertas_nuevas: int = 0
    rechazados: pd.DataFrame = field(default_factory=pd.DataFrame)


def entrenar_detector_simulacion():
    ref = generar_referencia_normal(REFERENCIA_N, REFERENCIA_SEMILLA)
    return DetectorAnomalias(**MODELO_SIM).entrenar(ref)


def evaluar_simulacion(detector):
    pred = detector.predecir(generar_evaluacion(EVALUACION_N, EVALUACION_SEMILLA))
    return evaluar_detector(pred)


def contexto_caracteristicas(fila, medianas):
    partes = []
    for c in CARACTERISTICAS:
        ref = float(medianas[c])
        if ref <= 0:
            continue
        razon = float(fila[c]) / ref
        if razon >= CONTEXTO_RAZON:
            partes.append(f"{c} {razon:,.0f}× la mediana")
        elif razon <= 1 / CONTEXTO_RAZON:
            partes.append(f"{c} {1 / max(razon, 1e-9):,.0f}× menor que la mediana")
    return partes


def construir_alertas(pred, medianas, modo, fuente):
    anom = pred[pred["estado"] == "Anomalía"]
    filas = []
    for idx, f in anom.iterrows():
        ctx = contexto_caracteristicas(f, medianas)
        regla = (f"Isolation Forest: puntuación {f['anomaly_score']:.3f} por debajo del umbral. "
                 + ("Contexto: " + "; ".join(ctx) + "." if ctx else "Sin valores extremos individuales."))
        filas.append(dict(
            evento_id=f["evento_id"], fecha=f.get("fecha"), ip_origen=f.get("ip_origen"),
            ip_destino=f.get("ip_destino"), puerto_destino=f.get("puerto_destino"),
            protocolo=f.get("protocolo"), bytes=f["bytes"], paquetes=f["paquetes"],
            duracion=f["duracion"], puertos=f["puertos"], anomaly_score=f["anomaly_score"],
            estado="Anomalía", severidad=severidad_por_puntuacion(f["anomaly_score"]),
            regla=regla, modo=modo, fuente=fuente,
            indice_csv=idx if modo == "csv" else None,
        ))
    return pd.DataFrame(filas)


def procesar_eventos(eventos, detector, modo, fuente, ruta=None):
    if eventos is None or eventos.empty:
        return Resultado()
    validos, rechazados = validar_eventos(eventos)
    if validos.empty:
        return Resultado(rechazados=rechazados)
    pred = detector.predecir(validos)
    db.guardar_eventos(pred, modo, fuente, ruta)
    nuevas = db.guardar_alertas(construir_alertas(pred, detector.medianas, modo, fuente), ruta)
    return Resultado(len(pred), int((pred["estado"] == "Anomalía").sum()), nuevas, rechazados)


def analizar_csv(contenido, nombre, ruta=None):
    df = leer_csv(contenido, nombre)
    digest = hashlib.sha1(contenido).hexdigest()
    fuente = f"{nombre}#{digest[:8]}"
    df["evento_id"] = [f"csv-{digest[:10]}-{i:05d}" for i in df.index]
    if "fecha" not in df.columns:
        df["fecha"] = None
    df["escenario"] = None
    validos, _ = validar_eventos(df)
    if len(validos) < 10:
        raise ValueError("El CSV necesita al menos 10 filas válidas.")
    detector = DetectorAnomalias(**MODELO_CSV).entrenar(validos)
    return fuente, procesar_eventos(df, detector, "csv", fuente, ruta)
