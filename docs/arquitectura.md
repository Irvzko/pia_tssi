# Arquitectura

```
Generador / CSV ─► validacion ─► modelo (Isolation Forest) ─► deteccion ─► SQLite
                                                                   │
                         dashboard (app.py) ◄── correlacion ◄──────┘
```

- **Interfaz** (`app.py`, `interfaz/`): Streamlit + Plotly. Conserva la paleta y el CSS originales.
  Las zonas que cambian solas usan `st.fragment(run_every=...)` (Streamlit 1.62 lo soporta).
- **Generador** (`generador/eventos.py`): crea lotes con ID único (`evt-<hex>`). IP privadas
  (192.168/16, 10/8) y de documentación (198.51.100/24, 203.0.113/24). No hay red real.
- **Modelo** (`modelo/isolation_forest.py`): `DetectorAnomalias` entrena una vez y `predecir`
  no modifica el modelo. El mismo `preparar_caracteristicas` se usa al entrenar y al predecir.
  `detectar_anomalias()` conserva el análisis original del CSV.
- **Servicios** (`servicios/`): `validacion` (IP, rangos, CSV), `deteccion` (valida → predice →
  crea alertas → guarda), `correlacion` (3 reglas), `kpi`, `exportacion`.
- **Persistencia** (`base_datos/database.py`): tablas `eventos`, `alertas`, `incidentes`, `notas`,
  `historial`. Consultas parametrizadas, transacciones, claves foráneas, índices, `PRAGMA user_version`.

## Sin duplicados al refrescar

El generador solo corre cuando toca el ciclo (intervalo configurable). Los eventos tienen ID único y
se guardan con `INSERT OR IGNORE`; una alerta por evento (`evento_id UNIQUE`). El modo CSV usa IDs
derivados del contenido del archivo, así que reabrirlo no duplica.

## Separación de modos

Cada registro guarda `modo` (`simulacion` o `csv`) y `fuente`. Los KPI, gráficas, correlación
e incidentes se calculan por modo; un incidente no mezcla alertas de ambos.
