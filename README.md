# CyberRadar FIME · Network Anomaly Detector TSSI

Prototipo académico de monitoreo defensivo. Detecta conexiones de red atípicas con
Isolation Forest, guarda alertas en SQLite y permite investigarlas en un dashboard Streamlit.

> **Alcance.** El modo Simulación genera telemetría **sintética**: no captura tráfico real,
> no envía paquetes y no se conecta a firewalls ni a ningún sistema. El modo CSV analiza un
> archivo histórico. No es un SOC de producción y no garantiza detectar intrusiones.

## Instalación

```bash
cd detector_anomalias
python3 -m venv venv && source venv/bin/activate   # si aún no tienes el entorno
pip install -r requirements.txt
```

## Ejecución

```bash
python -m streamlit run app.py
```

Pruebas (usan bases SQLite temporales, nunca `alertas.db`):

```bash
python -m unittest discover -s tests -t .
```

## Flujo

Generador o CSV → validación → modelo → eventos detectados → alertas → SQLite →
correlación → investigación → dashboard.

## Estructura

| Ruta | Función |
|---|---|
| `app.py` | Único punto de entrada (interfaz) |
| `config.py` | Parámetros: modelo, generador, severidades, correlación |
| `generador/eventos.py` | Eventos sintéticos |
| `modelo/isolation_forest.py` | Detector (entrena una vez, predice) |
| `servicios/` | Validación, detección, correlación, KPI, exportación |
| `base_datos/database.py` | SQLite con migraciones no destructivas |
| `interfaz/` | Paleta original y gráficas nuevas |
| `tests/` | Pruebas `unittest` |
| `docs/` | Arquitectura, modelo y guías |

Documentación: [arquitectura](docs/arquitectura.md) · [modelo](docs/modelo.md) ·
[guía de simulación](docs/guia_simulacion.md) · [investigación de alertas](docs/guia_investigacion.md) ·
[limitaciones](docs/limitaciones.md)

## Notas sobre tu base de datos

`alertas.db` no se borra. Al abrir la app se migra a la versión 2 del esquema (añade tablas y
columnas; conserva tus alertas anteriores, que quedan como origen "CSV").
**Haz una copia de `alertas.db` antes de la primera ejecución.**
