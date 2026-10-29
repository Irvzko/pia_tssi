import pandas as pd


def eventos_por_minuto(fechas, ahora=None, ventana_s=60):
    t = pd.to_datetime(pd.Series(fechas), errors="coerce").dropna()
    if t.empty:
        return None
    if ahora is not None:
        desde = pd.Timestamp(ahora) - pd.Timedelta(seconds=ventana_s)
        return float(((t >= desde) & (t <= pd.Timestamp(ahora))).sum() * 60 / ventana_s)
    segundos = (t.max() - t.min()).total_seconds()
    return float((len(t) - 1) * 60 / segundos) if len(t) > 1 and segundos > 0 else 0.0


def calcular_kpis(ind, fechas=(), ahora=None):
    total, anom = ind["eventos"], ind["anomalias"]
    return dict(
        eventos=total, anomalias=anom, normales=total - anom,
        pct_normal=(total - anom) / total * 100 if total else 0.0,
        pct_anomalo=anom / total * 100 if total else 0.0,
        pendientes=ind["pendientes"], incidentes_abiertos=ind["incidentes_abiertos"],
        eventos_min=eventos_por_minuto(fechas, ahora),
    )
