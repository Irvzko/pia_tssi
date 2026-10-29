# Limitaciones conocidas

- Los datos de simulación son sintéticos; las métricas no se extrapolan a redes reales.
- Isolation Forest es no supervisado: marca lo raro, no lo malicioso. Hay falsos positivos y negativos.
- En modo CSV el modelo se entrena con el mismo archivo y marca el 15 % más atípico aunque todo sea normal.
- `trafico.csv` no tiene columna de fecha: en ese modo la actividad se grafica por registro y no hay
  gráficas por intervalo, eventos por minuto ni correlación (la app lo indica). Un CSV propio con `fecha` e IP sí las usa.
- No hay captura de paquetes, ingesta de logs en tiempo real, integración con firewalls ni respuesta automática.
- La simulación corre mientras hay una pestaña abierta; no es un servicio en segundo plano.
- La correlación es de tres reglas simples, no un SIEM.
- Las gráficas usan los últimos 2000 eventos (`MAX_EVENTOS_GRAFICAS`).
