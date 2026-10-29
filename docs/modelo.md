# Modelo

Detector principal: **Isolation Forest** (scikit-learn) sobre `bytes`, `paquetes`, `duracion`, `puertos`
(`puertos` = puertos distintos por conexión). Parámetros en `config.py`.

| Modo | Entrenamiento | Parámetros |
|---|---|---|
| CSV | El propio archivo (como la versión original) | `n_estimators=100, contamination=0.15, random_state=42` |
| Simulación | 3000 eventos **normales** de referencia, una sola vez | `n_estimators=100, contamination=0.02, random_state=42` |

- Las anomalías **no** se añaden al entrenamiento.
- Valores nulos, infinitos, negativos o no numéricos: las filas se rechazan con motivo; no se imputan.
- `anomaly_score` es la `decision_function`: menor = más atípico. **No es una probabilidad de ataque.**
- `prediccion` y `estado` los produce el modelo. `escenario` (etiqueta sintética) se guarda aparte y
  solo sirve para evaluar.

## Evaluación (conjuntos sintéticos independientes del entrenamiento)

Con tres semillas distintas se obtuvo recall ≈ 98 %, precisión ≈ 87–92 % y ≈ 1,4–2,2 % de falsos
positivos entre el tráfico normal. Son datos sintéticos creados por nosotros: no demuestran el rendimiento en
una red real.

## Severidad

Prioridad de revisión por corte de puntuación (`CORTES_SEVERIDAD` en `config.py`):
< −0,115 Crítica · < −0,085 Alta · < −0,05 Media · < −0,02 Baja · resto Informativa.
No indica certeza de intrusión.

## «Contexto» de la alerta

Compara cada característica con la mediana de referencia y señala las que son ≥3× mayores o menores.
Es descriptivo; no es la explicación interna del modelo.
