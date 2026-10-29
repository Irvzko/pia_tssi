from pathlib import Path

RAIZ = Path(__file__).resolve().parent
RUTA_CSV = RAIZ / "datos" / "trafico.csv"

CARACTERISTICAS = ["bytes", "paquetes", "duracion", "puertos"]

# Modelo: CSV se entrena con el propio archivo; simulación con tráfico normal
MODELO_CSV = dict(n_estimators=100, contamination=0.15, random_state=42)
MODELO_SIM = dict(n_estimators=100, contamination=0.02, random_state=42)
REFERENCIA_N = 3000
REFERENCIA_SEMILLA = 7
EVALUACION_N = 3000
EVALUACION_SEMILLA = 99

GENERADOR = dict(intervalo_s=2.0, eventos_por_ciclo=5, proporcion_atipica=0.06)
ESCENARIOS = {
    "pico_volumen": 0.30,
    "duracion_atipica": 0.20,
    "escaneo_puertos": 0.25,
    "rafaga_conexiones": 0.25,
}

# Severidad según la puntuación (menor = más atípico)
SEVERIDADES = ["Informativa", "Baja", "Media", "Alta", "Crítica"]
CORTES_SEVERIDAD = [(-0.115, "Crítica"), (-0.085, "Alta"), (-0.05, "Media"), (-0.02, "Baja")]

ESTADOS_ALERTA = ["Nueva", "En investigación", "Resuelta", "Descartada"]
ESTADOS_INCIDENTE = ["Abierto", "En investigación", "Cerrado"]
CIERRES = ("Resuelta", "Descartada", "Cerrado")

# Correlación
CORRELACION = dict(
    ventana_s=120,
    min_anomalias=3,
    umbral_frecuencia=15,
    min_anom_frecuencia=2,
)

CONTEXTO_RAZON = 3.0

MAX_EVENTOS_GRAFICAS = 2000
MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_CSV_FILAS = 50_000


def severidad_por_puntuacion(puntuacion):
    for corte, nombre in CORTES_SEVERIDAD:
        if puntuacion < corte:
            return nombre
    return "Informativa"
