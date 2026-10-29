import ipaddress
import unittest
from datetime import datetime

from generador.eventos import COLUMNAS, GeneradorEventos, generar_referencia_normal


class PruebasGenerador(unittest.TestCase):
    def test_ciclo_tiene_columnas_y_cantidad(self):
        df = GeneradorEventos(eventos_por_ciclo=7, semilla=1).generar_ciclo(datetime(2026, 1, 1))
        self.assertEqual(list(df.columns), COLUMNAS)
        self.assertEqual(len(df), 7)

    def test_ids_unicos_entre_ciclos_y_generadores(self):
        ids = []
        for semilla in (1, 1):
            gen = GeneradorEventos(semilla=semilla)
            for _ in range(20):
                ids += list(gen.generar_ciclo()["evento_id"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_ips_validas_privadas_o_documentacion(self):
        df = GeneradorEventos(proporcion_atipica=0.3, semilla=2).generar_lote(1500)
        for ip in set(df["ip_origen"]) | set(df["ip_destino"]):
            dir_ip = ipaddress.ip_address(ip)
            en_doc = any(dir_ip in ipaddress.ip_network(r) for r in ("198.51.100.0/24", "203.0.113.0/24"))
            self.assertTrue(dir_ip.is_private or en_doc, ip)

    def test_proporcion_atipica_configurable(self):
        for p in (0.0, 0.05, 0.2):
            df = GeneradorEventos(proporcion_atipica=p, semilla=3).generar_lote(6000)
            real = (df["escenario"] != "normal").mean()
            self.assertAlmostEqual(real, p, delta=0.04)

    def test_referencia_solo_normal(self):
        self.assertTrue((generar_referencia_normal(500, 1)["escenario"] == "normal").all())

    def test_valores_en_rango(self):
        df = GeneradorEventos(proporcion_atipica=0.3, semilla=4).generar_lote(1000)
        self.assertTrue((df[["bytes", "paquetes", "duracion", "puertos"]] > 0).all().all())
        self.assertTrue(df["puerto_destino"].between(1, 65535).all())

    def test_parametros_invalidos(self):
        gen = GeneradorEventos()
        with self.assertRaises(ValueError):
            gen.configurar(intervalo_s=0)
        with self.assertRaises(ValueError):
            gen.configurar(eventos_por_ciclo=0)
        with self.assertRaises(ValueError):
            gen.configurar(proporcion_atipica=0.9)

    def test_pausa_y_reanudacion_conservan_estado(self):
        gen = GeneradorEventos(proporcion_atipica=0.3, eventos_por_ciclo=3, semilla=5)
        antes = [gen.generar_ciclo() for _ in range(5)]
        despues = [gen.generar_ciclo() for _ in range(5)]
        ids = [i for df in antes + despues for i in df["evento_id"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_episodios_usan_un_solo_origen(self):
        df = GeneradorEventos(proporcion_atipica=0.3, semilla=6).generar_lote(3000)
        escaneo = df[df["escenario"] == "escaneo_puertos"]
        self.assertGreater(len(escaneo), 0)
        repetidos = (escaneo["ip_origen"] == escaneo["ip_origen"].shift()).mean()
        self.assertGreater(repetidos, 0.5)


if __name__ == "__main__":
    unittest.main()
