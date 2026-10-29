import ipaddress
import io

import numpy as np
import pandas as pd

from config import CARACTERISTICAS, MAX_CSV_BYTES, MAX_CSV_FILAS

PROTOCOLOS = {"TCP", "UDP", "ICMP"}


def _ip_valida(valor):
    try:
        ipaddress.ip_address(str(valor).strip())
        return True
    except ValueError:
        return False


def validar_eventos(eventos):
    faltantes = [c for c in CARACTERISTICAS if c not in eventos.columns]
    if faltantes:
        raise ValueError("Faltan columnas: " + ", ".join(faltantes))
    df = eventos.copy()
    motivo = pd.Series("", index=df.index, dtype=object)

    def marcar(mascara, texto):
        motivo[mascara & (motivo == "")] = texto

    X = df[CARACTERISTICAS].apply(pd.to_numeric, errors="coerce")
    marcar(X.isna().any(axis=1) | np.isinf(X).any(axis=1), "característica vacía o no numérica")
    marcar((X < 0).any(axis=1), "característica negativa")
    for col in ("ip_origen", "ip_destino"):
        if col in df.columns:
            lleno = df[col].notna() & (df[col].astype(str).str.strip() != "")
            marcar(lleno & ~df[col].map(_ip_valida), f"{col} no es una IP válida")
    if "protocolo" in df.columns:
        lleno = df["protocolo"].notna()
        marcar(lleno & ~df["protocolo"].astype(str).str.upper().isin(PROTOCOLOS), "protocolo no válido")
    if "puerto_destino" in df.columns:
        p = pd.to_numeric(df["puerto_destino"], errors="coerce")
        marcar(df["puerto_destino"].notna() & (p.isna() | (p < 0) | (p > 65535)), "puerto fuera de rango")

    malas = motivo != ""
    validos = df[~malas].copy()
    validos[CARACTERISTICAS] = X[~malas]
    rechazados = df[malas].copy()
    rechazados["motivo"] = motivo[malas]
    return validos, rechazados


def leer_csv(contenido, nombre="datos.csv"):
    if not str(nombre).lower().endswith(".csv"):
        raise ValueError("El archivo debe ser .csv")
    if len(contenido) > MAX_CSV_BYTES:
        raise ValueError(f"El archivo supera {MAX_CSV_BYTES // (1024 * 1024)} MB.")
    try:
        df = pd.read_csv(io.BytesIO(contenido))
    except Exception as e:
        raise ValueError(f"No se pudo leer el CSV: {e}") from None
    if df.empty:
        raise ValueError("El CSV no contiene registros.")
    if len(df) > MAX_CSV_FILAS:
        raise ValueError(f"El CSV supera {MAX_CSV_FILAS:,} filas.")
    faltantes = [c for c in CARACTERISTICAS if c not in df.columns]
    if faltantes:
        raise ValueError("Faltan columnas en el CSV: " + ", ".join(faltantes))
    if "fecha" in df.columns:
        fechas = pd.to_datetime(df["fecha"], errors="coerce")
        texto = fechas.dt.strftime("%Y-%m-%d %H:%M:%S.000").astype(object)
        df["fecha"] = texto.where(fechas.notna(), None)
    return df
