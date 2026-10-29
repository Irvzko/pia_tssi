import unittest
from datetime import datetime, timedelta

import pandas as pd

from servicios.exportacion import COLUMNAS_ALERTAS, COLUMNAS_EVENTOS, a_csv
from servicios.kpi import calcular_kpis, eventos_por_minuto

AHORA = datetime(2026, 1, 1, 12, 0, 0)


class PruebasKpi(unittest.TestCase):
    def test_sin_datos_da_ceros(self):
        k = calcular_kpis(dict(eventos=0, anomalias=0, pendientes=0, incidentes_abiertos=0), [], AHORA)
        self.assertEqual((k["eventos"], k["anomalias"], k["pct_normal"], k["pct_anomalo"]), (0, 0, 0.0, 0.0))
        self.assertIsNone(k["eventos_min"])

    def test_porcentajes(self):
        k = calcular_kpis(dict(eventos=200, anomalias=30, pendientes=4, incidentes_abiertos=2))
        self.assertEqual((k["normales"], k["pct_normal"], k["pct_anomalo"]), (170, 85.0, 15.0))
        self.assertEqual((k["pendientes"], k["incidentes_abiertos"]), (4, 2))

    def test_eventos_por_minuto_con_ahora(self):
        fechas = [AHORA - timedelta(seconds=s) for s in (1, 10, 30, 59, 61, 300)]
        self.assertEqual(eventos_por_minuto(fechas, AHORA), 4.0)

    def test_eventos_por_minuto_pausado_es_cero(self):
        fechas = [AHORA - timedelta(seconds=s) for s in (500, 600)]
        self.assertEqual(eventos_por_minuto(fechas, AHORA), 0.0)

    def test_eventos_por_minuto_por_periodo(self):
        fechas = [AHORA + timedelta(seconds=s) for s in (0, 30, 60, 120)]
        self.assertEqual(eventos_por_minuto(fechas), 1.5)

    def test_sin_marcas_de_tiempo(self):
        self.assertIsNone(eventos_por_minuto([None, None]))
        self.assertIsNone(eventos_por_minuto([], AHORA))
        self.assertEqual(eventos_por_minuto([AHORA]), 0.0)

    def test_acepta_texto(self):
        self.assertEqual(eventos_por_minuto(["2026-01-01 11:59:30.000"], AHORA), 1.0)


class PruebasExportacion(unittest.TestCase):
    def test_solo_columnas_permitidas(self):
        df = pd.DataFrame([dict(fecha="x", ip_origen="1.1.1.1", bytes=1, escenario="pico", secreto="s",
                                estado="Normal")])
        csv = a_csv(df, COLUMNAS_EVENTOS).decode("utf-8-sig")
        self.assertNotIn("escenario", csv)
        self.assertNotIn("secreto", csv)
        self.assertTrue(csv.startswith("fecha,ip_origen,bytes,estado"))

    def test_protege_formulas(self):
        df = pd.DataFrame([dict(ip_origen="=1+1", ip_destino="@x", regla="-1", severidad="Alta")])
        csv = a_csv(df, COLUMNAS_ALERTAS).decode("utf-8-sig")
        self.assertIn("'=1+1", csv)
        self.assertIn("'@x", csv)

    def test_exporta_vacio_y_numeros_negativos(self):
        self.assertTrue(a_csv(pd.DataFrame(), COLUMNAS_ALERTAS).decode("utf-8-sig").strip() in ("", '""'))
        df = pd.DataFrame([dict(anomaly_score=-0.2)])
        self.assertIn("-0.2", a_csv(df, COLUMNAS_ALERTAS).decode("utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
