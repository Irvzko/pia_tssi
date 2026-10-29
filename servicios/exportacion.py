import pandas as pd

COLUMNAS_EVENTOS = ["fecha", "ip_origen", "ip_destino", "puerto_destino", "protocolo", "bytes",
                    "paquetes", "duracion", "puertos", "estado", "anomaly_score", "severidad"]
COLUMNAS_ALERTAS = ["id", "fecha", "modo", "fuente", "ip_origen", "ip_destino", "puerto_destino",
                    "protocolo", "bytes", "paquetes", "duracion", "puertos", "anomaly_score",
                    "severidad", "estado_revision", "regla", "incidente_id", "evento_id"]


def a_csv(df, columnas):
    salida = df.reindex(columns=[c for c in columnas if c in df.columns]).copy()
    for c in salida.columns:
        if not pd.api.types.is_numeric_dtype(salida[c]) and not pd.api.types.is_datetime64_any_dtype(salida[c]):
            salida[c] = salida[c].map(
                lambda v: "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v)
    return salida.to_csv(index=False).encode("utf-8-sig")
