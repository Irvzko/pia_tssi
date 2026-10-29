import unittest

import pandas as pd

from config import MAX_CSV_BYTES
from servicios.validacion import leer_csv, validar_eventos


def fila(**kw):
    base = dict(ip_origen="192.168.1.1", ip_destino="10.0.0.5", protocolo="TCP", puerto_destino=443,
                bytes=100, paquetes=5, duracion=1.0, puertos=2)
    base.update(kw)
    return base


class PruebasValidacion(unittest.TestCase):
    def test_filas_validas_pasan(self):
        v, r = validar_eventos(pd.DataFrame([fila(), fila()]))
        self.assertEqual((len(v), len(r)), (2, 0))

    def test_rechaza_con_motivo(self):
        malos = [fila(ip_origen="999.1.1.1"), fila(ip_destino="abc"), fila(bytes=-1),
                 fila(duracion=None), fila(paquetes="x"), fila(puertos=float("inf")),
                 fila(protocolo="XYZ"), fila(puerto_destino=70000)]
        v, r = validar_eventos(pd.DataFrame([fila()] + malos))
        self.assertEqual(len(v), 1)
        self.assertEqual(len(r), len(malos))
        self.assertTrue((r["motivo"] != "").all())

    def test_faltan_columnas(self):
        with self.assertRaises(ValueError):
            validar_eventos(pd.DataFrame({"bytes": [1]}))

    def test_solo_caracteristicas_es_valido(self):
        v, _ = validar_eventos(pd.DataFrame([dict(bytes=1, paquetes=1, duracion=1, puertos=1)]))
        self.assertEqual(len(v), 1)

    def test_csv_valido(self):
        df = leer_csv(b"bytes,paquetes,duracion,puertos\n1,2,3,4\n", "a.csv")
        self.assertEqual(len(df), 1)

    def test_csv_rechazos(self):
        with self.assertRaises(ValueError):
            leer_csv(b"bytes,paquetes\n1,2\n", "a.csv")
        with self.assertRaises(ValueError):
            leer_csv(b"", "a.csv")
        with self.assertRaises(ValueError):
            leer_csv(b"bytes,paquetes,duracion,puertos\n", "a.csv")
        with self.assertRaises(ValueError):
            leer_csv(b"x" * (MAX_CSV_BYTES + 1), "a.csv")
        with self.assertRaises(ValueError):
            leer_csv(b"bytes,paquetes,duracion,puertos\n1,2,3,4\n", "a.py")

    def test_csv_normaliza_fecha(self):
        df = leer_csv(b"fecha,bytes,paquetes,duracion,puertos\n2026-01-01 10:00:00,1,2,3,4\nmala,1,2,3,4\n", "a.csv")
        self.assertEqual(df["fecha"].iloc[0], "2026-01-01 10:00:00.000")
        self.assertTrue(pd.isna(df["fecha"].iloc[1]))


if __name__ == "__main__":
    unittest.main()
