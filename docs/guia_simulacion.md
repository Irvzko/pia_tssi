# Guía de la simulación

1. Elige **Simulación autónoma**.
2. En la barra lateral ajusta intervalo (1–10 s), eventos por ciclo (1–20) y % de eventos atípicos (0–30).
3. Pulsa **Iniciar simulación**. Cada ciclo genera eventos, los analiza y guarda alertas.
4. **Pausar simulación** detiene la generación; el historial se conserva y al reanudar continúa sin repetir IDs.
5. Cambiar de modo pausa la simulación.

La simulación avanza mientras la página está abierta en el navegador. El % atípico es el de eventos
sintéticos con escenario (pico de volumen, duración larga, escaneo de puertos simulado, ráfaga de
conexiones); el modelo decide por su cuenta qué marca como anomalía.

Demostración sugerida: 1 s, 10 eventos por ciclo, 25 %, unos 30 s → ver KPI y gráficas → pestaña
Alertas → abrir una → pestaña Incidentes → crear un incidente desde un grupo correlacionado.
