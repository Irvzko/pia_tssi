import hashlib

import pandas as pd

from config import CORRELACION, SEVERIDADES


def _sesiones(df, clave, ventana_s):
    grupos = []
    for valor, g in df.groupby(clave):
        g = g.sort_values("_t")
        corte = g["_t"].diff().dt.total_seconds().fillna(0) > ventana_s
        for _, s in g.groupby(corte.cumsum()):
            grupos.append((valor, s))
    return grupos


def _grupo(regla, clave, s, explicacion):
    anom = s[s["estado"] == "Anomalía"]
    sevs = [x for x in anom.get("severidad", pd.Series(dtype=object)).dropna()]
    sev = max(sevs, key=SEVERIDADES.index) if sevs else "Informativa"
    ids = sorted(anom["evento_id"])
    return dict(
        id=hashlib.sha1("|".join([regla] + ids).encode()).hexdigest()[:10],
        regla=regla, clave=str(clave), n_eventos=len(s), n_anomalias=len(anom),
        inicio=s["fecha"].min(), fin=s["fecha"].max(), severidad=sev,
        evento_ids=list(s["evento_id"]), anomalia_ids=ids,
        alerta_ids=[int(a) for a in anom["alerta_id"].dropna()] if "alerta_id" in anom else [],
        incidente_ids=sorted({int(i) for i in anom["incidente_id"].dropna()}) if "incidente_id" in anom else [],
        explicacion=explicacion,
    )


def correlacionar(eventos, config=None):
    c = {**CORRELACION, **(config or {})}
    if eventos is None or eventos.empty or "fecha" not in eventos.columns:
        return []
    df = eventos.dropna(subset=["fecha", "ip_origen"]).copy()
    if df.empty:
        return []
    df["_t"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["_t"])
    grupos, vistos = [], set()

    def añadir(g):
        if g["alerta_ids"] and frozenset(g["anomalia_ids"]) not in vistos:
            vistos.add(frozenset(g["anomalia_ids"]))
            grupos.append(g)

    anom = df[df["estado"] == "Anomalía"]
    for ip, s in _sesiones(anom, "ip_origen", c["ventana_s"]):
        if len(s) >= c["min_anomalias"]:
            añadir(_grupo("Anomalías repetidas de un origen", ip, s,
                          f"{len(s)} anomalías de {ip} con menos de {c['ventana_s']} s entre sí."))
    for ip, s in _sesiones(df, "ip_origen", c["ventana_s"]):
        n_anom = int((s["estado"] == "Anomalía").sum())
        if len(s) >= c["umbral_frecuencia"] and n_anom >= c["min_anom_frecuencia"]:
            añadir(_grupo("Aumento de frecuencia de un origen", ip, s,
                          f"{len(s)} eventos de {ip} en una sesión, {n_anom} anómalos "
                          f"(umbral: {c['umbral_frecuencia']} eventos)."))
    destino = anom.dropna(subset=["puerto_destino", "ip_destino"]).copy()
    destino["_clave"] = destino["ip_destino"] + ":" + destino["puerto_destino"].astype(int).astype(str)
    for k, s in _sesiones(destino, "_clave", c["ventana_s"]):
        if len(s) >= c["min_anomalias"]:
            añadir(_grupo("Anomalías hacia el mismo destino y puerto", k, s,
                          f"{len(s)} anomalías hacia {k} en la misma ventana, "
                          f"de {s['ip_origen'].nunique()} origen(es)."))
    return sorted(grupos, key=lambda g: g["fin"], reverse=True)
