from pathlib import Path

import pandas as pd
from sklearn.ensemble import IsolationForest

from config import CARACTERISTICAS, MODELO_CSV, RUTA_CSV


def preparar_caracteristicas(datos):
    faltantes = [c for c in CARACTERISTICAS if c not in datos.columns]
    if faltantes:
        raise ValueError("Faltan características: " + ", ".join(faltantes))
    X = datos[CARACTERISTICAS].apply(pd.to_numeric, errors="coerce").astype(float)
    return X.replace([float("inf"), float("-inf")], float("nan"))


def _exigir_validos(X):
    if X.isna().any().any() or (X < 0).any().any():
        raise ValueError("Hay valores nulos, infinitos o negativos en las características.")


class DetectorAnomalias:

    def __init__(self, n_estimators=100, contamination=0.15, random_state=42):
        self.modelo = IsolationForest(
            n_estimators=n_estimators, contamination=contamination,
            random_state=random_state,
        )
        self.entrenado = False
        self.n_entrenamiento = 0
        self.medianas = None

    def entrenar(self, datos):
        X = preparar_caracteristicas(datos)
        _exigir_validos(X)
        if len(X) < 10:
            raise ValueError("Se necesitan al menos 10 registros para entrenar.")
        self.modelo.fit(X)
        self.medianas = X.median()
        self.n_entrenamiento = len(X)
        self.entrenado = True
        return self

    def predecir(self, datos):
        if not self.entrenado:
            raise RuntimeError("El modelo no está entrenado.")
        X = preparar_caracteristicas(datos)
        _exigir_validos(X)
        salida = datos.copy()
        if X.empty:
            salida["prediccion"], salida["anomaly_score"], salida["estado"] = [], [], []
            return salida
        salida["prediccion"] = self.modelo.predict(X)
        salida["anomaly_score"] = self.modelo.decision_function(X)
        salida["estado"] = salida["prediccion"].map({1: "Normal", -1: "Anomalía"})
        return salida


def detectar_anomalias(ruta=None, datos=None):
    if datos is None:
        ruta = Path(ruta) if ruta else RUTA_CSV
        if not ruta.exists():
            raise FileNotFoundError(f"No se encontró el archivo de tráfico: {ruta}")
        datos = pd.read_csv(ruta)
    if datos.empty:
        raise ValueError("El archivo de tráfico no contiene registros.")
    X = preparar_caracteristicas(datos)
    vacias = X.columns[X.notna().sum() == 0].tolist()
    if vacias:
        raise ValueError("Sin valores numéricos válidos en: " + ", ".join(vacias))
    datos = datos.copy()
    datos[X.columns] = X.fillna(X.median())
    return DetectorAnomalias(**MODELO_CSV).entrenar(datos).predecir(datos)


def evaluar_detector(pred):
    real = pred["escenario"] != "normal"
    dado = pred["estado"] == "Anomalía"
    tp, fp = int((real & dado).sum()), int((~real & dado).sum())
    fn, tn = int((real & ~dado).sum()), int((~real & ~dado).sum())
    return dict(
        tp=tp, fp=fp, fn=fn, tn=tn,
        precision=tp / (tp + fp) if tp + fp else 0.0,
        recall=tp / (tp + fn) if tp + fn else 0.0,
        fpr=fp / (fp + tn) if fp + tn else 0.0,
    )
