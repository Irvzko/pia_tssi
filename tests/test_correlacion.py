import unittest

import pandas as pd

from servicios.correlacion import correlacionar
from tests.comun import evento


def df(filas):
    d = pd.DataFrame(filas)
    d["alerta_id"] = d.apply(lambda f: 100 + int(f["evento_id"][4:]) if f["estado"] == "Anomalía" else None, axis=1)
    d["incidente_id"] = None
    d["severidad"] = d["estado"].map({"Anomalía": "Alta"})
    return d


class PruebasCorrelacion(unittest.TestCase):
    def test_agrupa_anomalias_cercanas_del_mismo_origen(self):
        ev = [evento(i, ip="198.51.100.7", estado="Anomalía", seg=i * 5) for i in range(4)]
        ev += [evento(10 + i, ip=f"192.168.1.{i}", seg=i) for i in range(5)]
        grupos = correlacionar(df(ev))
        self.assertEqual(len(grupos), 1)
        g = grupos[0]
        self.assertEqual((g["n_anomalias"], g["clave"]), (4, "198.51.100.7"))
        self.assertEqual(len(g["alerta_ids"]), 4)
        self.assertIn("4 anomalías", g["explicacion"])

    def test_ip_repetida_normal_no_genera_grupo(self):
        ev = [evento(i, ip="192.168.1.10", seg=i) for i in range(10)]
        self.assertEqual(correlacionar(df(ev)), [])

    def test_pocas_anomalias_no_agrupan(self):
        ev = [evento(i, ip=f"198.51.100.{i}", estado="Anomalía", seg=i * 500,
                     destino=f"10.0.0.{i}") for i in range(2)]
        self.assertEqual(correlacionar(df(ev)), [])

    def test_ventana_separa_sesiones(self):
        ev = [evento(i, ip="198.51.100.7", estado="Anomalía", seg=i * 500) for i in range(4)]
        self.assertEqual(correlacionar(df(ev)), [])

    def test_umbral_configurable(self):
        ev = [evento(i, ip=f"198.51.100.{i}", estado="Anomalía", seg=i * 5) for i in range(2)]
        ev = [dict(e, ip_destino="10.0.0.5", puerto_destino=22) for e in ev]
        self.assertEqual(correlacionar(df(ev)), [])
        self.assertEqual(len(correlacionar(df(ev), dict(min_anomalias=2))), 1)

    def test_regla_destino_y_puerto(self):
        ev = [evento(i, ip=f"198.51.100.{i}", estado="Anomalía", seg=i * 5, destino="10.0.0.8", puerto=22)
              for i in range(3)]
        g = correlacionar(df(ev))
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["clave"], "10.0.0.8:22")

    def test_aumento_de_frecuencia(self):
        ev = [evento(i, ip="192.168.1.20", seg=i) for i in range(18)]
        ev += [evento(100, ip="192.168.1.20", estado="Anomalía", seg=3),
               evento(101, ip="192.168.1.20", estado="Anomalía", seg=4)]
        g = correlacionar(df(ev))
        self.assertEqual([x["regla"] for x in g], ["Aumento de frecuencia de un origen"])

    def test_sin_datos_o_sin_fechas(self):
        self.assertEqual(correlacionar(pd.DataFrame()), [])
        self.assertEqual(correlacionar(None), [])
        sin = df([evento(i, estado="Anomalía") for i in range(4)]).assign(fecha=None)
        self.assertEqual(correlacionar(sin), [])

    def test_marca_alertas_ya_en_incidente(self):
        ev = df([evento(i, ip="198.51.100.7", estado="Anomalía", seg=i) for i in range(3)])
        ev["incidente_id"] = 5
        self.assertEqual(correlacionar(ev)[0]["incidente_ids"], [5])


if __name__ == "__main__":
    unittest.main()
