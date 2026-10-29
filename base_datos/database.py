import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

from config import (CIERRES, ESTADOS_ALERTA, ESTADOS_INCIDENTE, SEVERIDADES,
                    severidad_por_puntuacion)

RUTA_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_DB = RUTA_PROYECTO / "base_datos" / "alertas.db"
VERSION_ESQUEMA = 2
_LISTAS = set()


def _ahora():
    return datetime.now().isoformat(timespec="seconds")


def _py(valor):
    if valor is None:
        return None
    if hasattr(valor, "item"):
        valor = valor.item()
    if isinstance(valor, float) and valor != valor:
        return None
    return valor


def conectar(ruta=None):
    ruta = Path(ruta or RUTA_DB)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def transaccion(ruta=None):
    con = conectar(ruta)
    try:
        con.execute("BEGIN")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _df(con, sql, params=()):
    return pd.DataFrame([dict(f) for f in con.execute(sql, params).fetchall()])


def _columnas(con, tabla):
    return {f["name"] for f in con.execute(f"PRAGMA table_info({tabla})")}


def _mig_1(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS alertas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evento_id TEXT NOT NULL UNIQUE,
            fecha TEXT NOT NULL,
            bytes INTEGER,
            paquetes INTEGER,
            duracion REAL,
            puertos INTEGER,
            anomaly_score REAL,
            estado TEXT NOT NULL
        )
    """)


def _mig_2(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS eventos (
            evento_id TEXT PRIMARY KEY,
            fecha TEXT,
            modo TEXT NOT NULL,
            fuente TEXT NOT NULL,
            ip_origen TEXT, ip_destino TEXT,
            puerto_destino INTEGER, protocolo TEXT,
            bytes INTEGER NOT NULL, paquetes INTEGER NOT NULL,
            duracion REAL NOT NULL, puertos INTEGER NOT NULL,
            escenario TEXT,
            prediccion INTEGER, anomaly_score REAL, estado TEXT,
            registrado TEXT NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS incidentes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            severidad TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'Abierto',
            modo TEXT NOT NULL,
            resumen TEXT, criterio TEXT, motivo_cierre TEXT,
            creado TEXT NOT NULL, actualizado TEXT NOT NULL
        )
    """)
    nuevas = {
        "ip_origen": "TEXT", "ip_destino": "TEXT", "puerto_destino": "INTEGER",
        "protocolo": "TEXT", "severidad": "TEXT", "regla": "TEXT",
        "estado_revision": "TEXT NOT NULL DEFAULT 'Nueva'", "motivo_cierre": "TEXT",
        "incidente_id": "INTEGER REFERENCES incidentes(id)", "actualizado": "TEXT",
        "modo": "TEXT NOT NULL DEFAULT 'csv'", "fuente": "TEXT",
    }
    existentes = _columnas(con, "alertas")
    for nombre, tipo in nuevas.items():
        if nombre not in existentes:
            con.execute(f"ALTER TABLE alertas ADD COLUMN {nombre} {tipo}")
    con.execute("""
        CREATE TABLE IF NOT EXISTS notas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alerta_id INTEGER REFERENCES alertas(id),
            incidente_id INTEGER REFERENCES incidentes(id),
            texto TEXT NOT NULL, fecha TEXT NOT NULL,
            CHECK (alerta_id IS NOT NULL OR incidente_id IS NOT NULL)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entidad TEXT NOT NULL CHECK (entidad IN ('alerta', 'incidente')),
            entidad_id INTEGER NOT NULL,
            anterior TEXT, nuevo TEXT NOT NULL, motivo TEXT, fecha TEXT NOT NULL
        )
    """)
    indices = [
        "alertas(severidad)", "alertas(estado_revision)", "alertas(fecha)",
        "alertas(ip_origen)", "alertas(incidente_id)", "alertas(modo)",
        "eventos(fecha)", "eventos(modo, fuente)", "eventos(ip_origen)",
        "notas(alerta_id)", "notas(incidente_id)", "historial(entidad, entidad_id)",
    ]
    for i in indices:
        nombre = "ix_" + i.split("(")[0] + "_" + i.split("(")[1].rstrip(")").replace(", ", "_")
        con.execute(f"CREATE INDEX IF NOT EXISTS {nombre} ON {i}")
    con.execute("UPDATE alertas SET fuente = 'trafico.csv' WHERE fuente IS NULL")
    for f in con.execute("SELECT id, anomaly_score FROM alertas WHERE severidad IS NULL").fetchall():
        sev = severidad_por_puntuacion(f["anomaly_score"] if f["anomaly_score"] is not None else 0)
        con.execute("UPDATE alertas SET severidad = ? WHERE id = ?", (sev, f["id"]))
    con.execute("""
        INSERT INTO historial (entidad, entidad_id, anterior, nuevo, motivo, fecha)
        SELECT 'alerta', a.id, NULL, 'Nueva', 'Alerta importada del esquema anterior', a.fecha
        FROM alertas a
        WHERE NOT EXISTS (SELECT 1 FROM historial h WHERE h.entidad = 'alerta' AND h.entidad_id = a.id)
    """)


def inicializar_base_datos(ruta=None):
    clave = str(Path(ruta or RUTA_DB).resolve())
    if clave in _LISTAS and Path(clave).exists():
        return
    with transaccion(ruta) as con:
        version = con.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            _mig_1(con)
        if version < 2:
            _mig_2(con)
        if version < VERSION_ESQUEMA:
            con.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
    _LISTAS.add(clave)


def _historial(con, entidad, entidad_id, anterior, nuevo, motivo=None):
    con.execute(
        "INSERT INTO historial (entidad, entidad_id, anterior, nuevo, motivo, fecha) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (entidad, entidad_id, anterior, nuevo, motivo or None, _ahora()),
    )


def guardar_eventos(eventos, modo, fuente, ruta=None):
    if eventos is None or eventos.empty:
        return 0
    inicializar_base_datos(ruta)
    ahora = _ahora()
    filas = []
    for f in eventos.to_dict("records"):
        filas.append((
            f["evento_id"], _py(f.get("fecha")), modo, fuente,
            _py(f.get("ip_origen")), _py(f.get("ip_destino")),
            _py(f.get("puerto_destino")), _py(f.get("protocolo")),
            int(f["bytes"]), int(f["paquetes"]), float(f["duracion"]), int(f["puertos"]),
            _py(f.get("escenario")), _py(f.get("prediccion")),
            _py(f.get("anomaly_score")), _py(f.get("estado")), ahora,
        ))
    with transaccion(ruta) as con:
        antes = con.total_changes
        con.executemany("""
            INSERT OR IGNORE INTO eventos (
                evento_id, fecha, modo, fuente, ip_origen, ip_destino, puerto_destino,
                protocolo, bytes, paquetes, duracion, puertos, escenario, prediccion,
                anomaly_score, estado, registrado)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, filas)
        return con.total_changes - antes


def cargar_eventos(modo, fuente=None, limite=2000, ruta=None):
    inicializar_base_datos(ruta)
    sql = ("SELECT e.*, a.id AS alerta_id, a.severidad, a.estado_revision, a.incidente_id "
           "FROM eventos e LEFT JOIN alertas a ON a.evento_id = e.evento_id WHERE e.modo = ?")
    params = [modo]
    if fuente:
        sql += " AND e.fuente = ?"
        params.append(fuente)
    sql += " ORDER BY e.rowid DESC LIMIT ?"
    params.append(int(limite))
    with transaccion(ruta) as con:
        df = _df(con, sql, params)
    return df.iloc[::-1].reset_index(drop=True)


def obtener_evento(evento_id, ruta=None):
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        f = con.execute("SELECT * FROM eventos WHERE evento_id = ?", (evento_id,)).fetchone()
    return dict(f) if f else None


def eventos_en_ventana(modo, inicio, fin, ip_origen=None, limite=500, ruta=None):
    inicializar_base_datos(ruta)
    sql = ("SELECT e.*, a.id AS alerta_id, a.severidad FROM eventos e "
           "LEFT JOIN alertas a ON a.evento_id = e.evento_id "
           "WHERE e.modo = ? AND e.fecha >= ? AND e.fecha <= ?")
    params = [modo, inicio, fin]
    if ip_origen:
        sql += " AND e.ip_origen = ?"
        params.append(ip_origen)
    sql += " ORDER BY e.fecha LIMIT ?"
    params.append(int(limite))
    with transaccion(ruta) as con:
        return _df(con, sql, params)


def _fusionar_legado(con, f):
    if f.get("indice_csv") is None or str(f.get("fuente", "")).split("#")[0] != "trafico.csv":
        return False
    if con.execute("SELECT 1 FROM alertas WHERE evento_id = ?", (f["evento_id"],)).fetchone():
        return True
    prefijo = (f"{int(f['indice_csv'])}|{int(f['bytes'])}|{int(f['paquetes'])}|"
               f"{float(f['duracion'])}|{int(f['puertos'])}|")
    fila = con.execute("SELECT id FROM alertas WHERE evento_id LIKE ? AND ip_origen IS NULL",
                       (prefijo + "%",)).fetchone()
    if not fila:
        return False
    con.execute(
        "UPDATE alertas SET evento_id = ?, ip_origen = ?, ip_destino = ?, protocolo = ?, "
        "regla = COALESCE(regla, ?), fuente = ?, actualizado = ? WHERE id = ?",
        (f["evento_id"], _py(f.get("ip_origen")), _py(f.get("ip_destino")),
         _py(f.get("protocolo")), _py(f.get("regla")), f["fuente"], _ahora(), fila["id"]),
    )
    return True


def guardar_alertas(alertas, ruta=None):
    if alertas is None or alertas.empty:
        return 0
    inicializar_base_datos(ruta)
    nuevas = 0
    with transaccion(ruta) as con:
        for f in alertas.to_dict("records"):
            f = {k: _py(v) for k, v in f.items()}
            if f.get("modo") == "csv" and _fusionar_legado(con, f):
                continue
            cur = con.execute("""
                INSERT OR IGNORE INTO alertas (
                    evento_id, fecha, bytes, paquetes, duracion, puertos, anomaly_score,
                    estado, ip_origen, ip_destino, puerto_destino, protocolo, severidad,
                    regla, estado_revision, modo, fuente, actualizado)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'Nueva',?,?,?)
            """, (
                f["evento_id"], f.get("fecha") or _ahora(), int(f["bytes"]),
                int(f["paquetes"]), float(f["duracion"]), int(f["puertos"]),
                f.get("anomaly_score"), f.get("estado") or "Anomalía",
                f.get("ip_origen"), f.get("ip_destino"), f.get("puerto_destino"),
                f.get("protocolo"), f.get("severidad"), f.get("regla"),
                f["modo"], f.get("fuente"), _ahora(),
            ))
            if cur.rowcount == 1:
                nuevas += 1
                _historial(con, "alerta", cur.lastrowid, None, "Nueva", "Creada por el detector")
    return nuevas


def obtener_alertas(ruta=None):
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        cur = con.execute("""
            SELECT id, fecha, bytes, paquetes, duracion, puertos, anomaly_score, estado
            FROM alertas ORDER BY id DESC
        """)
        columnas = [c[0] for c in cur.description]
        filas = [tuple(f) for f in cur.fetchall()]
    return columnas, filas


def _escapar(texto):
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _donde_alertas(filtros):
    f = filtros or {}
    cond, params = [], []
    if f.get("modo"):
        cond.append("a.modo = ?")
        params.append(f["modo"])
    for campo, col in (("severidades", "a.severidad"), ("estados", "a.estado_revision")):
        if f.get(campo):
            cond.append(f"{col} IN ({','.join('?' * len(f[campo]))})")
            params += list(f[campo])
    if f.get("desde"):
        cond.append("substr(a.fecha, 1, 10) >= ?")
        params.append(str(f["desde"]))
    if f.get("hasta"):
        cond.append("substr(a.fecha, 1, 10) <= ?")
        params.append(str(f["hasta"]))
    if f.get("ip"):
        cond.append("(a.ip_origen LIKE ? ESCAPE '\\' OR a.ip_destino LIKE ? ESCAPE '\\')")
        patron = f"%{_escapar(str(f['ip']).strip())}%"
        params += [patron, patron]
    if f.get("incidente_id"):
        cond.append("a.incidente_id = ?")
        params.append(int(f["incidente_id"]))
    return (" WHERE " + " AND ".join(cond)) if cond else "", params


def contar_alertas(filtros=None, ruta=None):
    inicializar_base_datos(ruta)
    donde, params = _donde_alertas(filtros)
    with transaccion(ruta) as con:
        return con.execute(f"SELECT COUNT(*) FROM alertas a{donde}", params).fetchone()[0]


def consultar_alertas(filtros=None, limite=50, offset=0, ruta=None):
    inicializar_base_datos(ruta)
    donde, params = _donde_alertas(filtros)
    with transaccion(ruta) as con:
        return _df(con, f"""
            SELECT a.id, a.fecha, a.modo, a.fuente, a.ip_origen, a.ip_destino,
                   a.puerto_destino, a.protocolo, a.bytes, a.paquetes, a.duracion,
                   a.puertos, a.anomaly_score, a.severidad, a.estado_revision,
                   a.regla, a.incidente_id, a.evento_id
            FROM alertas a{donde} ORDER BY a.id DESC LIMIT ? OFFSET ?
        """, params + [int(limite), int(offset)])


def obtener_alerta(alerta_id, ruta=None):
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        f = con.execute("SELECT * FROM alertas WHERE id = ?", (int(alerta_id),)).fetchone()
    return dict(f) if f else None


def cambiar_estado_alerta(alerta_id, nuevo, motivo="", ruta=None):
    if nuevo not in ESTADOS_ALERTA:
        raise ValueError(f"Estado no válido: {nuevo}")
    motivo = (motivo or "").strip()
    if nuevo in CIERRES and not motivo:
        raise ValueError(f"Indica el motivo para marcar la alerta como {nuevo}.")
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        f = con.execute("SELECT estado_revision FROM alertas WHERE id = ?", (int(alerta_id),)).fetchone()
        if not f:
            raise ValueError("La alerta no existe.")
        if f["estado_revision"] == nuevo:
            return False
        con.execute(
            "UPDATE alertas SET estado_revision = ?, motivo_cierre = ?, actualizado = ? WHERE id = ?",
            (nuevo, motivo if nuevo in CIERRES else None, _ahora(), int(alerta_id)),
        )
        _historial(con, "alerta", int(alerta_id), f["estado_revision"], nuevo, motivo)
    return True


def agregar_nota(texto, alerta_id=None, incidente_id=None, ruta=None):
    texto = (texto or "").strip()
    if not texto:
        raise ValueError("La nota está vacía.")
    if len(texto) > 2000:
        raise ValueError("La nota no puede superar 2000 caracteres.")
    if (alerta_id is None) == (incidente_id is None):
        raise ValueError("Indica una alerta o un incidente.")
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        cur = con.execute(
            "INSERT INTO notas (alerta_id, incidente_id, texto, fecha) VALUES (?, ?, ?, ?)",
            (alerta_id, incidente_id, texto, _ahora()),
        )
        return cur.lastrowid


def obtener_notas(alerta_id=None, incidente_id=None, ruta=None):
    inicializar_base_datos(ruta)
    col, valor = ("alerta_id", alerta_id) if alerta_id is not None else ("incidente_id", incidente_id)
    with transaccion(ruta) as con:
        return _df(con, f"SELECT id, fecha, texto FROM notas WHERE {col} = ? ORDER BY id", (valor,))


def obtener_historial(entidad, entidad_id, ruta=None):
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        return _df(con, "SELECT fecha, anterior, nuevo, motivo FROM historial "
                        "WHERE entidad = ? AND entidad_id = ? ORDER BY id", (entidad, int(entidad_id)))


def _rango(sev):
    return SEVERIDADES.index(sev) if sev in SEVERIDADES else 0


def _validar_alertas(con, alerta_ids, incidente_id=None):
    ids = sorted({int(i) for i in alerta_ids})
    if not ids:
        raise ValueError("Selecciona al menos una alerta.")
    filas = con.execute(
        f"SELECT id, severidad, modo, incidente_id FROM alertas WHERE id IN ({','.join('?' * len(ids))})",
        ids).fetchall()
    if len(filas) != len(ids):
        raise ValueError("Alguna alerta no existe.")
    for f in filas:
        if f["incidente_id"] not in (None, incidente_id):
            raise ValueError(f"La alerta {f['id']} ya pertenece al incidente {f['incidente_id']}.")
    if len({f["modo"] for f in filas}) > 1:
        raise ValueError("No se mezclan alertas de simulación y de CSV en un incidente.")
    return ids, filas


def _vincular(con, incidente_id, filas):
    for f in filas:
        con.execute("UPDATE alertas SET incidente_id = ?, actualizado = ? WHERE id = ?",
                    (incidente_id, _ahora(), f["id"]))
        if con.execute("SELECT estado_revision FROM alertas WHERE id = ?", (f["id"],)).fetchone()[0] == "Nueva":
            con.execute("UPDATE alertas SET estado_revision = 'En investigación' WHERE id = ?", (f["id"],))
            _historial(con, "alerta", f["id"], "Nueva", "En investigación",
                       f"Incluida en el incidente {incidente_id}")


def crear_incidente(titulo, alerta_ids, resumen="", criterio="Manual", ruta=None):
    titulo = (titulo or "").strip()
    if not titulo:
        raise ValueError("El incidente necesita un título.")
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        ids, filas = _validar_alertas(con, alerta_ids)
        sev = max((f["severidad"] for f in filas), key=_rango)
        ahora = _ahora()
        cur = con.execute(
            "INSERT INTO incidentes (titulo, severidad, estado, modo, resumen, criterio, creado, actualizado) "
            "VALUES (?, ?, 'Abierto', ?, ?, ?, ?, ?)",
            (titulo, sev or "Informativa", filas[0]["modo"], resumen, criterio, ahora, ahora),
        )
        iid = cur.lastrowid
        _historial(con, "incidente", iid, None, "Abierto", f"Creado con {len(ids)} alerta(s)")
        _vincular(con, iid, filas)
        return iid


def agregar_alertas_a_incidente(incidente_id, alerta_ids, ruta=None):
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        inc = con.execute("SELECT * FROM incidentes WHERE id = ?", (int(incidente_id),)).fetchone()
        if not inc:
            raise ValueError("El incidente no existe.")
        ids, filas = _validar_alertas(con, alerta_ids, int(incidente_id))
        if filas[0]["modo"] != inc["modo"]:
            raise ValueError("La alerta es de otro origen que el incidente.")
        nuevas = [f for f in filas if f["incidente_id"] is None]
        _vincular(con, int(incidente_id), nuevas)
        sev = max([inc["severidad"]] + [f["severidad"] for f in nuevas], key=_rango)
        con.execute("UPDATE incidentes SET severidad = ?, actualizado = ? WHERE id = ?",
                    (sev, _ahora(), int(incidente_id)))
        if nuevas:
            _historial(con, "incidente", int(incidente_id), None, inc["estado"],
                       f"Se añadieron {len(nuevas)} alerta(s)")
        return len(nuevas)


def cambiar_estado_incidente(incidente_id, nuevo, motivo="", ruta=None):
    if nuevo not in ESTADOS_INCIDENTE:
        raise ValueError(f"Estado no válido: {nuevo}")
    motivo = (motivo or "").strip()
    if nuevo in CIERRES and not motivo:
        raise ValueError("Indica el motivo para cerrar el incidente.")
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        f = con.execute("SELECT estado FROM incidentes WHERE id = ?", (int(incidente_id),)).fetchone()
        if not f:
            raise ValueError("El incidente no existe.")
        if f["estado"] == nuevo:
            return False
        con.execute("UPDATE incidentes SET estado = ?, motivo_cierre = ?, actualizado = ? WHERE id = ?",
                    (nuevo, motivo if nuevo in CIERRES else None, _ahora(), int(incidente_id)))
        _historial(con, "incidente", int(incidente_id), f["estado"], nuevo, motivo)
    return True


def listar_incidentes(modo=None, estados=None, limite=50, offset=0, ruta=None):
    inicializar_base_datos(ruta)
    cond, params = [], []
    if modo:
        cond.append("i.modo = ?")
        params.append(modo)
    if estados:
        cond.append(f"i.estado IN ({','.join('?' * len(estados))})")
        params += list(estados)
    donde = (" WHERE " + " AND ".join(cond)) if cond else ""
    with transaccion(ruta) as con:
        return _df(con, f"""
            SELECT i.id, i.titulo, i.severidad, i.estado, i.modo, i.creado, i.actualizado,
                   (SELECT COUNT(*) FROM alertas a WHERE a.incidente_id = i.id) AS alertas
            FROM incidentes i{donde} ORDER BY i.id DESC LIMIT ? OFFSET ?
        """, params + [int(limite), int(offset)])


def obtener_incidente(incidente_id, ruta=None):
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        f = con.execute("SELECT * FROM incidentes WHERE id = ?", (int(incidente_id),)).fetchone()
    return dict(f) if f else None


def eventos_de_incidente(incidente_id, ruta=None):
    inicializar_base_datos(ruta)
    with transaccion(ruta) as con:
        return _df(con, """
            SELECT e.*, a.id AS alerta_id, a.severidad FROM eventos e
            JOIN alertas a ON a.evento_id = e.evento_id
            WHERE a.incidente_id = ? ORDER BY e.fecha, e.rowid
        """, (int(incidente_id),))


def indicadores(modo, fuente=None, ruta=None):
    inicializar_base_datos(ruta)
    sql = "SELECT COUNT(*), COALESCE(SUM(estado = 'Anomalía'), 0) FROM eventos WHERE modo = ?"
    params = [modo]
    if fuente:
        sql += " AND fuente = ?"
        params.append(fuente)
    with transaccion(ruta) as con:
        total, anomalias = con.execute(sql, params).fetchone()
        pendientes = con.execute(
            "SELECT COUNT(*) FROM alertas WHERE modo = ? AND estado_revision = 'Nueva'", (modo,)
        ).fetchone()[0]
        abiertos = con.execute(
            "SELECT COUNT(*) FROM incidentes WHERE modo = ? AND estado != 'Cerrado'", (modo,)
        ).fetchone()[0]
    return dict(eventos=total, anomalias=int(anomalias), pendientes=pendientes, incidentes_abiertos=abiertos)
