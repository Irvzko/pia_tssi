# Guía de investigación

**Alertas** (pestaña): filtra por origen, severidad, estado, fechas e IP; pagina; exporta CSV.
Elige una alerta para ver: motivo de detección, resumen, características frente a la mediana,
eventos relacionados del mismo origen (±120 s), notas e historial.

- **Estados:** Nueva, En investigación, Resuelta, Descartada. Resuelta/Descartada exigen motivo.
  Nada se borra; cada cambio queda en el historial.
- **Notas:** hasta 2000 caracteres, persisten.
- **Incidente:** crea uno desde la alerta o añádela a uno abierto.

**Incidentes** (pestaña): arriba, grupos propuestos por la correlación con su explicación; abajo, la
lista y el detalle (alertas, cronología, estado con motivo al cerrar, notas, historial, exportación).

## Reglas de correlación (`CORRELACION` en `config.py`)

1. ≥3 anomalías del mismo origen con ≤120 s entre ellas.
2. ≥15 eventos de un origen en una sesión con ≥2 anomalías.
3. ≥3 anomalías hacia el mismo destino:puerto en la misma ventana.

Una IP repetida sin anomalías no forma grupo. Un incidente es una agrupación de trabajo, no una
confirmación de intrusión.
