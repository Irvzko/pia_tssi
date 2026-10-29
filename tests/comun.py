import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from servicios import deteccion

_DETECTOR = None


def detector():
    global _DETECTOR
    if _DETECTOR is None:
        _DETECTOR = deteccion.entrenar_detector_simulacion()
    return _DETECTOR


class ConBD(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.ruta = Path(self._tmp.name) / "prueba.db"


def evento(i=0, ip="192.168.1.10", estado="Normal", seg=0, score=0.1, destino="10.0.0.5",
           puerto=443, base=datetime(2026, 1, 1, 12, 0, 0)):
    return dict(
        evento_id=f"evt-{i:06d}", fecha=(base + timedelta(seconds=seg)).isoformat(sep=" ", timespec="milliseconds"),
        ip_origen=ip, ip_destino=destino, puerto_destino=puerto, protocolo="TCP",
        bytes=4000, paquetes=50, duracion=2.5, puertos=3, escenario="normal",
        prediccion=1 if estado == "Normal" else -1, anomaly_score=score, estado=estado,
    )


def tabla(filas):
    return pd.DataFrame(filas)


def alerta_desde(ev, severidad="Alta", modo="simulacion", fuente="generador", **extra):
    a = dict(ev, severidad=severidad, regla="Regla de prueba", modo=modo, fuente=fuente, indice_csv=None)
    a.update(extra)
    return a


def crear_base_legada(ruta):
    con = sqlite3.connect(ruta)
    con.execute("""CREATE TABLE alertas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, evento_id TEXT NOT NULL UNIQUE,
        fecha TEXT NOT NULL, bytes INTEGER, paquetes INTEGER, duracion REAL,
        puertos INTEGER, anomaly_score REAL, estado TEXT NOT NULL)""")
    con.executemany(
        "INSERT INTO alertas (evento_id, fecha, bytes, paquetes, duracion, puertos, anomaly_score, estado) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [("30|900000|11000|0.3|250|-0.119", "2026-10-16T18:06:53", 900000, 11000, 0.3, 250, -0.119, "Anomalía"),
         ("2|2800|38|3.2|2|-0.0007", "2026-10-16T18:06:53", 2800, 38, 3.2, 2, -0.0007, "Anomalía")])
    con.commit()
    con.close()
