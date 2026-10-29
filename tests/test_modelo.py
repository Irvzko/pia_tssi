import unittest
from pathlib import Path

import pandas as pd

from config import EVALUACION_N, EVALUACION_SEMILLA
from generador.eventos import generar_evaluacion
from modelo.isolation_forest import (DetectorAnomalias, detectar_anomalias, evaluar_detector,
                                     preparar_caracteristicas)
from tests.comun import detector


class PruebasModelo(unittest.TestCase):
    def test_prediccion_tiene_columnas(self):
        pred = detector().predecir(generar_evaluacion(200, 1))
        for c in ("prediccion", "anomaly_score", "estado"):
            self.assertIn(c, pred.columns)
        self.assertTrue(set(pred["estado"]) <= {"Normal", "Anomalía"})

    def test_conserva_columnas_e_indice_originales(self):
        datos = generar_evaluacion(50, 2)
        pred = detector().predecir(datos)
        self.assertTrue(set(datos.columns) <= set(pred.columns))
        self.assertTrue((pred.index == datos.index).all())

    def test_predecir_no_reentrena(self):
        det = detector()
        n, med = det.n_entrenamiento, det.medianas.copy()
        datos = generar_evaluacion(300, 3)
        a = det.predecir(datos)
        b = det.predecir(datos)
        self.assertEqual(det.n_entrenamiento, n)
        self.assertTrue(det.medianas.equals(med))
        self.assertTrue(a["anomaly_score"].equals(b["anomaly_score"]))

    def test_metricas_con_conjunto_independiente(self):
        m = evaluar_detector(detector().predecir(generar_evaluacion(EVALUACION_N, EVALUACION_SEMILLA + 1)))
        self.assertGreater(m["recall"], 0.9)
        self.assertLess(m["fpr"], 0.05)

    def test_preprocesamiento_igual_en_entrenar_y_predecir(self):
        datos = generar_evaluacion(30, 4).astype({"bytes": object})
        X = preparar_caracteristicas(datos)
        self.assertTrue((X.dtypes == float).all())

    def test_datos_invalidos(self):
        det = detector()
        base = generar_evaluacion(20, 5)
        with self.assertRaises(ValueError):
            det.predecir(base.drop(columns=["bytes"]))
        malo = base.astype({"bytes": object})
        for valor in (None, -5, "abc", float("inf")):
            malo.loc[0, "bytes"] = valor
            with self.assertRaises(ValueError):
                det.predecir(malo)

    def test_entrenar_con_pocos_datos_falla(self):
        with self.assertRaises(ValueError):
            DetectorAnomalias().entrenar(generar_evaluacion(5, 6))

    def test_predecir_sin_entrenar_falla(self):
        with self.assertRaises(RuntimeError):
            DetectorAnomalias().predecir(generar_evaluacion(20, 7))

    def test_prediccion_vacia(self):
        pred = detector().predecir(generar_evaluacion(20, 8).iloc[0:0])
        self.assertTrue(pred.empty)

    def test_funcion_original_sobre_csv(self):
        datos = detectar_anomalias()
        self.assertEqual(len(datos), 35)
        self.assertEqual(int((datos["estado"] == "Anomalía").sum()), 6)
        self.assertTrue((datos.loc[30:34, "estado"] == "Anomalía").all())

    def test_funcion_original_errores(self):
        with self.assertRaises(FileNotFoundError):
            detectar_anomalias(Path("/no/existe.csv"))
        with self.assertRaises(ValueError):
            detectar_anomalias(datos=pd.DataFrame({"bytes": []}))
        with self.assertRaises(ValueError):
            detectar_anomalias(datos=pd.DataFrame({"bytes": [1] * 20}))


if __name__ == "__main__":
    unittest.main()
