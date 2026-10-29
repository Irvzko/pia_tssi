import sqlite3
import unittest

from base_datos import database as db
from tests.comun import ConBD, alerta_desde, crear_base_legada, evento, tabla


def sembrar(ruta, n=3, ip="192.168.1.10", sev="Alta", desde=0, **kw):
    evs = [evento(desde + i, ip=ip, estado="Anomalía", seg=i, score=-0.1, **kw) for i in range(n)]
    db.guardar_eventos(tabla(evs), "simulacion", "generador", ruta)
    db.guardar_alertas(tabla([alerta_desde(e, sev) for e in evs]), ruta)
    return list(db.consultar_alertas({"ip": ip}, 100, 0, ruta)["id"][::-1])


class PruebasEsquema(ConBD):
    def test_base_nueva(self):
        db.inicializar_base_datos(self.ruta)
        con = sqlite3.connect(self.ruta)
        tablas = {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"alertas", "eventos", "incidentes", "notas", "historial"} <= tablas)
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], db.VERSION_ESQUEMA)
        con.close()

    def test_migracion_conserva_alertas_anteriores(self):
        crear_base_legada(self.ruta)
        db.inicializar_base_datos(self.ruta)
        df = db.consultar_alertas(ruta=self.ruta)
        self.assertEqual(len(df), 2)
        self.assertEqual(set(df["estado_revision"]), {"Nueva"})
        self.assertEqual(set(df["modo"]), {"csv"})
        self.assertTrue(df["severidad"].notna().all())
        self.assertEqual(sorted(df["bytes"]), [2800, 900000])

    def test_migracion_es_idempotente(self):
        crear_base_legada(self.ruta)
        for _ in range(3):
            db._LISTAS.clear()
            db.inicializar_base_datos(self.ruta)
        self.assertEqual(db.contar_alertas(ruta=self.ruta), 2)
        self.assertEqual(len(db.obtener_historial("alerta", 1, self.ruta)), 1)

    def test_reiniciar_no_borra_datos(self):
        sembrar(self.ruta)
        db._LISTAS.clear()
        db.inicializar_base_datos(self.ruta)
        self.assertEqual(db.contar_alertas(ruta=self.ruta), 3)

    def test_integridad_referencial(self):
        db.inicializar_base_datos(self.ruta)
        with self.assertRaises(sqlite3.IntegrityError):
            with db.transaccion(self.ruta) as con:
                con.execute("INSERT INTO notas (alerta_id, texto, fecha) VALUES (999, 'x', 'y')")
        with self.assertRaises(sqlite3.IntegrityError):
            with db.transaccion(self.ruta) as con:
                con.execute("INSERT INTO notas (texto, fecha) VALUES ('x', 'y')")

    def test_transaccion_revierte_en_error(self):
        db.inicializar_base_datos(self.ruta)
        with self.assertRaises(RuntimeError):
            with db.transaccion(self.ruta) as con:
                con.execute("INSERT INTO historial (entidad, entidad_id, nuevo, fecha) VALUES ('alerta', 1, 'x', 'y')")
                raise RuntimeError
        with db.transaccion(self.ruta) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM historial").fetchone()[0], 0)


class PruebasEventosYAlertas(ConBD):
    def test_guardar_y_consultar_alertas(self):
        ids = sembrar(self.ruta, 3)
        self.assertEqual(len(ids), 3)
        a = db.obtener_alerta(ids[0], self.ruta)
        self.assertEqual(a["estado_revision"], "Nueva")
        self.assertEqual(a["evento_id"], "evt-000000")
        self.assertEqual(a["severidad"], "Alta")
        self.assertEqual(len(db.obtener_historial("alerta", ids[0], self.ruta)), 1)

    def test_deduplicacion_de_eventos_y_alertas(self):
        evs = [evento(i, estado="Anomalía") for i in range(4)]
        self.assertEqual(db.guardar_eventos(tabla(evs), "simulacion", "generador", self.ruta), 4)
        self.assertEqual(db.guardar_eventos(tabla(evs), "simulacion", "generador", self.ruta), 0)
        al = tabla([alerta_desde(e) for e in evs])
        self.assertEqual(db.guardar_alertas(al, self.ruta), 4)
        self.assertEqual(db.guardar_alertas(al, self.ruta), 0)
        self.assertEqual(db.contar_alertas(ruta=self.ruta), 4)

    def test_dedup_por_evento_no_por_ip(self):
        evs = [evento(i, ip="192.168.1.10", estado="Anomalía") for i in range(3)]
        db.guardar_eventos(tabla(evs), "simulacion", "generador", self.ruta)
        db.guardar_alertas(tabla([alerta_desde(e) for e in evs]), self.ruta)
        self.assertEqual(db.contar_alertas(ruta=self.ruta), 3)

    def test_prediccion_original_no_se_sobrescribe(self):
        e = evento(1, estado="Anomalía", score=-0.2)
        db.guardar_eventos(tabla([e]), "simulacion", "generador", self.ruta)
        db.guardar_eventos(tabla([dict(e, estado="Normal", anomaly_score=0.3)]), "simulacion", "generador", self.ruta)
        ev = db.obtener_evento("evt-000001", self.ruta)
        self.assertEqual((ev["estado"], ev["anomaly_score"]), ("Anomalía", -0.2))

    def test_sin_registros(self):
        db.inicializar_base_datos(self.ruta)
        self.assertEqual(db.indicadores("simulacion", ruta=self.ruta),
                         dict(eventos=0, anomalias=0, pendientes=0, incidentes_abiertos=0))
        self.assertTrue(db.cargar_eventos("simulacion", ruta=self.ruta).empty)
        self.assertTrue(db.consultar_alertas(ruta=self.ruta).empty)
        self.assertEqual(db.guardar_alertas(tabla([]), self.ruta), 0)
        self.assertIsNone(db.obtener_alerta(1, self.ruta))

    def test_indicadores(self):
        evs = [evento(i, estado="Anomalía" if i < 2 else "Normal") for i in range(5)]
        db.guardar_eventos(tabla(evs), "simulacion", "generador", self.ruta)
        db.guardar_alertas(tabla([alerta_desde(e) for e in evs[:2]]), self.ruta)
        ind = db.indicadores("simulacion", ruta=self.ruta)
        self.assertEqual((ind["eventos"], ind["anomalias"], ind["pendientes"]), (5, 2, 2))
        self.assertEqual(db.indicadores("csv", ruta=self.ruta)["eventos"], 0)

    def test_cargar_eventos_orden_y_limite(self):
        db.guardar_eventos(tabla([evento(i, seg=i) for i in range(10)]), "simulacion", "generador", self.ruta)
        df = db.cargar_eventos("simulacion", limite=4, ruta=self.ruta)
        self.assertEqual(list(df["evento_id"]), [f"evt-{i:06d}" for i in range(6, 10)])

    def test_filtros_y_paginacion(self):
        sembrar(self.ruta, 3, ip="192.168.1.10", sev="Alta")
        evs = [evento(10 + i, ip="192.168.1.99", estado="Anomalía", seg=100 + i) for i in range(2)]
        db.guardar_eventos(tabla(evs), "simulacion", "generador", self.ruta)
        db.guardar_alertas(tabla([alerta_desde(e, "Baja") for e in evs]), self.ruta)
        f = lambda **k: db.contar_alertas(k, self.ruta)
        self.assertEqual(f(), 5)
        self.assertEqual(f(severidades=["Alta"]), 3)
        self.assertEqual(f(ip="1.99"), 2)
        self.assertEqual(f(ip="%"), 0)
        self.assertEqual(f(modo="csv"), 0)
        self.assertEqual(f(desde="2026-01-01", hasta="2026-01-01"), 5)
        self.assertEqual(f(desde="2026-01-02"), 0)
        self.assertEqual(f(estados=["Resuelta"]), 0)
        p1 = db.consultar_alertas({}, 2, 0, self.ruta)
        p3 = db.consultar_alertas({}, 2, 4, self.ruta)
        self.assertEqual((len(p1), len(p3)), (2, 1))

    def test_consultas_parametrizadas_resisten_inyeccion(self):
        sembrar(self.ruta, 2)
        self.assertEqual(db.contar_alertas({"ip": "' OR 1=1 --"}, self.ruta), 0)
        self.assertEqual(db.contar_alertas(ruta=self.ruta), 2)

    def test_fusion_con_alertas_anteriores_del_csv(self):
        crear_base_legada(self.ruta)
        e = evento(0, estado="Anomalía", score=-0.119)
        e.update(evento_id="csv-x-00030", bytes=900000, paquetes=11000, duracion=0.3, puertos=250)
        a = alerta_desde(e, "Crítica", modo="csv", fuente="trafico.csv#abc", indice_csv=30)
        self.assertEqual(db.guardar_alertas(tabla([a]), self.ruta), 0)
        self.assertEqual(db.contar_alertas(ruta=self.ruta), 2)
        self.assertEqual(db.obtener_alerta(1, self.ruta)["evento_id"], "csv-x-00030")
        self.assertEqual(db.guardar_alertas(tabla([a]), self.ruta), 0)
        self.assertEqual(db.contar_alertas(ruta=self.ruta), 2)


class PruebasRevision(ConBD):
    def test_cambio_de_estado_con_historial(self):
        aid = sembrar(self.ruta, 1)[0]
        self.assertTrue(db.cambiar_estado_alerta(aid, "En investigación", "", self.ruta))
        self.assertTrue(db.cambiar_estado_alerta(aid, "Resuelta", "Falso positivo confirmado", self.ruta))
        a = db.obtener_alerta(aid, self.ruta)
        self.assertEqual((a["estado_revision"], a["motivo_cierre"]), ("Resuelta", "Falso positivo confirmado"))
        h = db.obtener_historial("alerta", aid, self.ruta)
        self.assertEqual(list(h["nuevo"]), ["Nueva", "En investigación", "Resuelta"])
        self.assertEqual(h["motivo"].iloc[-1], "Falso positivo confirmado")

    def test_motivo_obligatorio_y_estado_valido(self):
        aid = sembrar(self.ruta, 1)[0]
        for estado in ("Resuelta", "Descartada"):
            with self.assertRaises(ValueError):
                db.cambiar_estado_alerta(aid, estado, "  ", self.ruta)
        with self.assertRaises(ValueError):
            db.cambiar_estado_alerta(aid, "Inventado", "x", self.ruta)
        with self.assertRaises(ValueError):
            db.cambiar_estado_alerta(9999, "En investigación", "", self.ruta)
        self.assertEqual(db.obtener_alerta(aid, self.ruta)["estado_revision"], "Nueva")

    def test_mismo_estado_no_registra(self):
        aid = sembrar(self.ruta, 1)[0]
        self.assertFalse(db.cambiar_estado_alerta(aid, "Nueva", "", self.ruta))
        self.assertEqual(len(db.obtener_historial("alerta", aid, self.ruta)), 1)

    def test_descartar_conserva_el_registro(self):
        aid = sembrar(self.ruta, 1)[0]
        db.cambiar_estado_alerta(aid, "Descartada", "Prueba de laboratorio", self.ruta)
        self.assertEqual(db.contar_alertas(ruta=self.ruta), 1)
        self.assertIsNotNone(db.obtener_evento("evt-000000", self.ruta))

    def test_notas_persisten_tras_reabrir(self):
        aid = sembrar(self.ruta, 1)[0]
        db.agregar_nota("Revisé el origen", alerta_id=aid, ruta=self.ruta)
        db._LISTAS.clear()
        notas = db.obtener_notas(alerta_id=aid, ruta=self.ruta)
        self.assertEqual(list(notas["texto"]), ["Revisé el origen"])

    def test_notas_validas(self):
        aid = sembrar(self.ruta, 1)[0]
        for texto in ("", "   ", "x" * 2001):
            with self.assertRaises(ValueError):
                db.agregar_nota(texto, alerta_id=aid, ruta=self.ruta)
        with self.assertRaises(ValueError):
            db.agregar_nota("hola", ruta=self.ruta)
        with self.assertRaises(ValueError):
            db.agregar_nota("hola", alerta_id=aid, incidente_id=1, ruta=self.ruta)


class PruebasIncidentes(ConBD):
    def test_crear_incidente(self):
        ids = sembrar(self.ruta, 3)
        iid = db.crear_incidente("Ráfaga", ids[:2], "resumen", "Manual", self.ruta)
        inc = db.obtener_incidente(iid, self.ruta)
        self.assertEqual((inc["estado"], inc["severidad"], inc["modo"]), ("Abierto", "Alta", "simulacion"))
        rel = db.consultar_alertas({"incidente_id": iid}, 10, 0, self.ruta)
        self.assertEqual(sorted(rel["id"]), sorted(ids[:2]))
        self.assertEqual(set(rel["estado_revision"]), {"En investigación"})
        self.assertEqual(db.obtener_alerta(ids[2], self.ruta)["estado_revision"], "Nueva")
        self.assertEqual(db.indicadores("simulacion", ruta=self.ruta)["incidentes_abiertos"], 1)
        self.assertEqual(len(db.eventos_de_incidente(iid, self.ruta)), 2)

    def test_severidad_del_incidente_es_la_maxima(self):
        a = sembrar(self.ruta, 1, ip="192.168.1.1", sev="Baja")[0]
        b = sembrar(self.ruta, 1, ip="192.168.1.2", sev="Crítica", desde=50, puerto=80)[0]
        iid = db.crear_incidente("Mixto", [a, b], ruta=self.ruta)
        self.assertEqual(db.obtener_incidente(iid, self.ruta)["severidad"], "Crítica")

    def test_validaciones(self):
        ids = sembrar(self.ruta, 2)
        with self.assertRaises(ValueError):
            db.crear_incidente("", ids, ruta=self.ruta)
        with self.assertRaises(ValueError):
            db.crear_incidente("X", [], ruta=self.ruta)
        with self.assertRaises(ValueError):
            db.crear_incidente("X", [9999], ruta=self.ruta)
        db.crear_incidente("A", [ids[0]], ruta=self.ruta)
        with self.assertRaises(ValueError):
            db.crear_incidente("B", [ids[0]], ruta=self.ruta)
        self.assertEqual(len(db.listar_incidentes(ruta=self.ruta)), 1)

    def test_no_mezcla_simulacion_y_csv(self):
        sim = sembrar(self.ruta, 1)[0]
        e = evento(50, estado="Anomalía")
        db.guardar_eventos(tabla([e]), "csv", "a.csv#1", self.ruta)
        db.guardar_alertas(tabla([alerta_desde(e, modo="csv", fuente="a.csv#1")]), self.ruta)
        csv = db.consultar_alertas({"modo": "csv"}, 5, 0, self.ruta)["id"].iloc[0]
        with self.assertRaises(ValueError):
            db.crear_incidente("Mezcla", [sim, int(csv)], ruta=self.ruta)

    def test_anadir_alertas(self):
        ids = sembrar(self.ruta, 3)
        iid = db.crear_incidente("A", ids[:1], ruta=self.ruta)
        self.assertEqual(db.agregar_alertas_a_incidente(iid, ids, self.ruta), 2)
        self.assertEqual(db.agregar_alertas_a_incidente(iid, ids, self.ruta), 0)
        self.assertEqual(db.listar_incidentes(ruta=self.ruta)["alertas"].iloc[0], 3)

    def test_estado_del_incidente(self):
        ids = sembrar(self.ruta, 1)
        iid = db.crear_incidente("A", ids, ruta=self.ruta)
        with self.assertRaises(ValueError):
            db.cambiar_estado_incidente(iid, "Cerrado", "", self.ruta)
        self.assertTrue(db.cambiar_estado_incidente(iid, "Cerrado", "Sin impacto", self.ruta))
        self.assertEqual(db.indicadores("simulacion", ruta=self.ruta)["incidentes_abiertos"], 0)
        self.assertEqual(list(db.obtener_historial("incidente", iid, self.ruta)["nuevo"]), ["Abierto", "Cerrado"])

    def test_notas_del_incidente_persisten(self):
        ids = sembrar(self.ruta, 1)
        iid = db.crear_incidente("A", ids, ruta=self.ruta)
        db.agregar_nota("Nota del incidente", incidente_id=iid, ruta=self.ruta)
        db._LISTAS.clear()
        self.assertEqual(list(db.obtener_notas(incidente_id=iid, ruta=self.ruta)["texto"]), ["Nota del incidente"])


if __name__ == "__main__":
    unittest.main()
