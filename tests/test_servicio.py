import unittest
from pathlib import Path

import pandas as pd

from base_datos import database as db
from config import RUTA_CSV
from generador.eventos import GeneradorEventos
from servicios import deteccion
from tests.comun import ConBD, detector


class PruebasServicio(ConBD):
    def test_flujo_completo_simulacion(self):
        gen = GeneradorEventos(proporcion_atipica=0.2, eventos_por_ciclo=10, semilla=11)
        total = 0
        for _ in range(30):
            r = deteccion.procesar_eventos(gen.generar_ciclo(), detector(), "simulacion", "generador", self.ruta)
            total += r.eventos
        ind = db.indicadores("simulacion", ruta=self.ruta)
        self.assertEqual(ind["eventos"], total)
        self.assertGreater(ind["anomalias"], 0)
        self.assertEqual(db.contar_alertas(ruta=self.ruta), ind["anomalias"])
        for a in db.consultar_alertas({}, 500, 0, self.ruta).to_dict("records"):
            ev = db.obtener_evento(a["evento_id"], self.ruta)
            self.assertEqual(ev["estado"], "Anomalía")
            self.assertEqual(ev["anomaly_score"], a["anomaly_score"])
            self.assertIn(a["severidad"], ("Informativa", "Baja", "Media", "Alta", "Crítica"))
            self.assertTrue(a["regla"])

    def test_etiqueta_del_escenario_separada_de_la_prediccion(self):
        gen = GeneradorEventos(proporcion_atipica=0.3, eventos_por_ciclo=20, semilla=12)
        for _ in range(10):
            deteccion.procesar_eventos(gen.generar_ciclo(), detector(), "simulacion", "generador", self.ruta)
        ev = db.cargar_eventos("simulacion", ruta=self.ruta)
        self.assertTrue(set(ev["estado"]) <= {"Normal", "Anomalía"})
        self.assertTrue((ev["escenario"] != "normal").any())
        self.assertFalse((ev["estado"] == ev["escenario"]).any())

    def test_reprocesar_no_duplica(self):
        lote = GeneradorEventos(proporcion_atipica=0.3, semilla=13).generar_lote(200)
        a = deteccion.procesar_eventos(lote, detector(), "simulacion", "generador", self.ruta)
        b = deteccion.procesar_eventos(lote, detector(), "simulacion", "generador", self.ruta)
        self.assertGreater(a.alertas_nuevas, 0)
        self.assertEqual(b.alertas_nuevas, 0)
        self.assertEqual(db.indicadores("simulacion", ruta=self.ruta)["eventos"], 200)

    def test_pausa_y_reanudacion_conservan_historial(self):
        gen = GeneradorEventos(eventos_por_ciclo=5, semilla=14)
        for _ in range(4):
            deteccion.procesar_eventos(gen.generar_ciclo(), detector(), "simulacion", "generador", self.ruta)
        antes = db.indicadores("simulacion", ruta=self.ruta)["eventos"]
        db._LISTAS.clear()
        self.assertEqual(db.indicadores("simulacion", ruta=self.ruta)["eventos"], antes)
        for _ in range(2):
            deteccion.procesar_eventos(gen.generar_ciclo(), detector(), "simulacion", "generador", self.ruta)
        self.assertEqual(db.indicadores("simulacion", ruta=self.ruta)["eventos"], antes + 10)

    def test_filas_invalidas_se_rechazan_sin_romper(self):
        lote = GeneradorEventos(semilla=15).generar_lote(20)
        lote.loc[0, "ip_origen"] = "no-es-ip"
        lote.loc[1, "bytes"] = -4
        r = deteccion.procesar_eventos(lote, detector(), "simulacion", "generador", self.ruta)
        self.assertEqual((r.eventos, len(r.rechazados)), (18, 2))

    def test_lote_vacio_o_todo_invalido(self):
        self.assertEqual(deteccion.procesar_eventos(pd.DataFrame(), detector(), "simulacion", "g", self.ruta).eventos, 0)
        lote = GeneradorEventos(semilla=16).generar_lote(3)
        lote["bytes"] = -1
        r = deteccion.procesar_eventos(lote, detector(), "simulacion", "g", self.ruta)
        self.assertEqual((r.eventos, len(r.rechazados)), (0, 3))

    def test_analizar_csv_del_proyecto(self):
        contenido = Path(RUTA_CSV).read_bytes()
        fuente, r = deteccion.analizar_csv(contenido, "trafico.csv", self.ruta)
        self.assertEqual((r.eventos, r.anomalias, r.alertas_nuevas), (35, 6, 6))
        fuente2, r2 = deteccion.analizar_csv(contenido, "trafico.csv", self.ruta)
        self.assertEqual((fuente, r2.alertas_nuevas), (fuente2, 0))
        self.assertEqual(db.contar_alertas({"modo": "csv"}, self.ruta), 6)
        self.assertEqual(db.contar_alertas({"modo": "simulacion"}, self.ruta), 0)
        ev = db.cargar_eventos("csv", fuente, ruta=self.ruta)
        self.assertEqual(len(ev), 35)
        self.assertTrue(ev["fecha"].isna().all())

    def test_csv_con_filas_malas(self):
        filas = ["bytes,paquetes,duracion,puertos,ip_origen"] + [f"{4000 + i},50,2.5,3,192.168.1.{i + 1}" for i in range(20)]
        filas.append("500,5,1.0,2,999.9.9.9")
        _, r = deteccion.analizar_csv("\n".join(filas).encode(), "propio.csv", self.ruta)
        self.assertEqual((r.eventos, len(r.rechazados)), (20, 1))

    def test_csv_demasiado_corto(self):
        with self.assertRaises(ValueError):
            deteccion.analizar_csv(b"bytes,paquetes,duracion,puertos\n1,2,3,4\n", "corto.csv", self.ruta)

    def test_csv_no_mezcla_con_simulacion(self):
        deteccion.analizar_csv(Path(RUTA_CSV).read_bytes(), "trafico.csv", self.ruta)
        deteccion.procesar_eventos(GeneradorEventos(semilla=17).generar_lote(50), detector(), "simulacion", "generador", self.ruta)
        self.assertEqual(db.indicadores("csv", ruta=self.ruta)["eventos"], 35)
        self.assertEqual(db.indicadores("simulacion", ruta=self.ruta)["eventos"], 50)

    def test_regla_describe_caracteristicas_atipicas(self):
        ev = GeneradorEventos(proporcion_atipica=0.4, semilla=18).generar_lote(300)
        pred = detector().predecir(ev)
        al = deteccion.construir_alertas(pred, detector().medianas, "simulacion", "generador")
        self.assertFalse(al.empty)
        self.assertTrue(al["regla"].str.contains("Isolation Forest").all())
        self.assertTrue(al["regla"].str.contains("mediana").any())


if __name__ == "__main__":
    unittest.main()
