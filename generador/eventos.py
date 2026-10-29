import random
import uuid
from datetime import datetime, timedelta

import pandas as pd

from config import ESCENARIOS, GENERADOR

CLIENTES = [f"192.168.1.{n}" for n in range(10, 41)]
SERVIDORES = ["10.0.0.5", "10.0.0.8", "10.0.0.10", "10.0.0.12"]
EXTERNAS = [f"198.51.100.{n}" for n in range(1, 31)] + [f"203.0.113.{n}" for n in range(1, 31)]
PUERTOS = [443, 80, 53, 22, 3306, 8080, 123]
PESOS_PUERTOS = [45, 20, 10, 5, 5, 10, 5]
EPISODIOS = ("escaneo_puertos", "rafaga_conexiones")
COLUMNAS = [
    "evento_id", "fecha", "ip_origen", "ip_destino", "puerto_destino", "protocolo",
    "bytes", "paquetes", "duracion", "puertos", "escenario",
]


class GeneradorEventos:

    def __init__(self, intervalo_s=None, eventos_por_ciclo=None,
                 proporcion_atipica=None, semilla=None):
        self.rng = random.Random(semilla)
        self.intervalo_s = GENERADOR["intervalo_s"]
        self.eventos_por_ciclo = GENERADOR["eventos_por_ciclo"]
        self.proporcion_atipica = GENERADOR["proporcion_atipica"]
        self.configurar(intervalo_s=intervalo_s, eventos_por_ciclo=eventos_por_ciclo,
                        proporcion_atipica=proporcion_atipica)
        self._episodio = None

    def configurar(self, intervalo_s=None, eventos_por_ciclo=None, proporcion_atipica=None):
        if intervalo_s is not None:
            if intervalo_s <= 0:
                raise ValueError("El intervalo debe ser mayor que cero.")
            self.intervalo_s = float(intervalo_s)
        if eventos_por_ciclo is not None:
            if int(eventos_por_ciclo) < 1:
                raise ValueError("Debe haber al menos un evento por ciclo.")
            self.eventos_por_ciclo = int(eventos_por_ciclo)
        if proporcion_atipica is not None:
            if not 0 <= proporcion_atipica <= 0.5:
                raise ValueError("La proporción atípica debe estar entre 0 y 0.5.")
            self.proporcion_atipica = float(proporcion_atipica)

    def _normal(self):
        r = self.rng
        b = max(1500, int(r.gauss(4000, 800)))
        return dict(
            ip_origen=r.choice(CLIENTES), ip_destino=r.choice(SERVIDORES),
            puerto_destino=r.choices(PUERTOS, PESOS_PUERTOS)[0],
            protocolo=r.choices(["TCP", "UDP"], [70, 30])[0],
            bytes=b, paquetes=max(10, int(b / 80 + r.gauss(0, 4))),
            duracion=round(max(0.5, r.gauss(2.6, 0.35)), 2),
            puertos=r.choices([2, 3, 4, 5], [2, 4, 3, 1])[0],
            escenario="normal",
        )

    def _atipico(self, escenario, ip_origen, ip_destino):
        r = self.rng
        e = self._normal()
        e.update(escenario=escenario, ip_origen=ip_origen, ip_destino=ip_destino)
        if escenario == "pico_volumen":
            e["bytes"] = int(r.uniform(40_000, 1_500_000))
            e["paquetes"] = int(e["bytes"] / r.uniform(70, 100))
            e["duracion"] = round(r.uniform(0.3, 3.0), 2)
        elif escenario == "duracion_atipica":
            e["duracion"] = round(r.uniform(120, 900), 1)
            e["bytes"] = int(4000 + e["duracion"] * r.uniform(100, 400))
            e["paquetes"] = int(e["bytes"] / 80 + r.gauss(0, 4))
        elif escenario == "escaneo_puertos":
            e["puertos"] = r.randint(15, 500)
            e["bytes"] = r.randint(2000, 12000)
            e["paquetes"] = r.randint(60, 400)
            e["duracion"] = round(r.uniform(0.3, 3.0), 2)
            e["puerto_destino"] = r.randint(1024, 9999)
        else:
            e["duracion"] = round(r.uniform(0.05, 0.4), 2)
            e["paquetes"] = r.randint(300, 900)
            e["bytes"] = r.randint(30_000, 90_000)
            e["puertos"] = r.randint(2, 6)
        return e

    def _siguiente(self):
        r = self.rng
        if self._episodio:
            ep = self._episodio
            ep["restantes"] -= 1
            if ep["restantes"] <= 0:
                self._episodio = None
            return self._atipico(ep["escenario"], ep["origen"], ep["destino"])
        nombres, pesos = list(ESCENARIOS), list(ESCENARIOS.values())
        medio = sum(p * (6 if n in EPISODIOS else 1) for n, p in ESCENARIOS.items()) / sum(pesos)
        if r.random() < self.proporcion_atipica / medio:
            esc = r.choices(nombres, pesos)[0]
            origen = r.choice(EXTERNAS if r.random() < 0.5 else CLIENTES)
            destino = r.choice(SERVIDORES)
            if esc in EPISODIOS:
                self._episodio = dict(escenario=esc, origen=origen, destino=destino,
                                      restantes=r.randint(4, 8) - 1)
            return self._atipico(esc, origen, destino)
        return self._normal()

    def _lote(self, n, tiempos):
        filas = []
        for t in tiempos[:n]:
            e = self._siguiente()
            e["evento_id"] = "evt-" + uuid.uuid4().hex[:12]
            e["fecha"] = t.isoformat(sep=" ", timespec="milliseconds")
            filas.append(e)
        return pd.DataFrame(filas, columns=COLUMNAS)

    def generar_ciclo(self, ahora=None):
        ahora = ahora or datetime.now()
        n = self.eventos_por_ciclo
        saltos = sorted(self.rng.uniform(0, self.intervalo_s) for _ in range(n))
        tiempos = [ahora - timedelta(seconds=self.intervalo_s - s) for s in saltos]
        return self._lote(n, tiempos)

    def generar_lote(self, n, inicio=None, paso_s=0.4):
        inicio = inicio or datetime(2026, 1, 1)
        return self._lote(n, [inicio + timedelta(seconds=i * paso_s) for i in range(n)])


def generar_referencia_normal(n, semilla):
    return GeneradorEventos(proporcion_atipica=0, semilla=semilla).generar_lote(n)


def generar_evaluacion(n, semilla, proporcion=0.15):
    return GeneradorEventos(proporcion_atipica=proporcion, semilla=semilla).generar_lote(n)
