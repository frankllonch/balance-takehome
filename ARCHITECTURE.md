# Arquitectura

Documento para quien tenga que **cambiar** esto, no para quien tenga que
evaluarlo. El razonamiento de producto y los hallazgos están en
[`SOLUTION.md`](SOLUTION.md); el enunciado en [`README.md`](README.md) y el
formato de entrada en [`SCHEMA.md`](SCHEMA.md).

---

## 1 · La idea en una frase

El fichero de eventos es el **sistema de registro**: inmutable, la única
fuente de verdad. Todo lo demás (tramos de pantalla, métricas diarias, índice,
avisos) es **dato derivado**: una función pura y determinista de ese log. Nada
se guarda a medias, nada depende del reloj de ejecución, y borrar cualquier
derivado y recalcularlo devuelve exactamente lo mismo.

De ahí salen dos reglas que conviene no romper:

1. **Una derivación, un dueño.** Si dos sitios calculan la misma cosa, tarde o
   temprano discrepan. `daily_frame` asigna la semana; nadie más la recalcula.
2. **Núcleo sin framework.** `events`, `metrics`, `score` e `intelligence` no
   importan Streamlit ni Plotly. El dashboard y el CLI son adaptadores, y por eso
   pueden probarse por separado y no pueden desincronizarse.

---

## 2 · Capas

```
data/*.json          log de eventos · sistema de registro · inmutable
       │
       ▼
balance/events.py    CAPA 0 · reconstrucción
                     · máquina de estados de pantalla (contador de profundidad)
                     · pickups frente a vistazos
                     · atribución de tiempo a app y a dominio
                     → Timeline(intervals, usages, blocks, anomalies)
       │
       ▼
balance/metrics.py   CAPA 1 · agregación
                     · daily_frame(): una fila por día, ~40 columnas
                     · weekly_frame(): una fila por semana, con variaciones
                     · totals(), category_daily(), hourly_heat(), blocks_frame()
       │
       ▼
balance/score.py     CAPA 2 · índice 0–100
                     · cinco componentes ponderados + descomposición
       │
       ▼
balance/intelligence.py  CAPA 3 · decisión
                     · reglas de aviso (tutor) con presupuesto de silencio
                     · reglas de refuerzo (usuario y tutor) con cupo semanal
                     · nudge nocturno + replay sobre el historial
                     · month_replay(): estado del sistema día a día
       │
       ├──────────────┬──────────────────────────
       ▼              ▼
balance/run.py    app.py + balance/charts.py + balance/theme.py
CLI               dashboard Streamlit
```

`charts.py` y `theme.py` son presentación pura: reciben frames ya calculados y
no deciden nada.

---

## 3 · Invariantes

Los tests los fijan; si tocas el código y alguno cae, es una decisión de
producto, no un detalle a arreglar en silencio.

| Invariante | Dónde se prueba |
|---|---|
| Todo `SCREEN_ON` acaba clasificado como pickup o vistazo, sin perder ni duplicar | `test_metrics.py` |
| El screen time de un día es la suma exacta de sus tramos | `test_metrics.py` |
| Pantalla en vigilia + offline en vigilia = ventana de vigilia | `test_metrics.py` |
| Los bloqueos por tipo suman el total | `test_data_contract.py` |
| El índice está en [0, 100] y sus pesos suman 1 | `test_score.py` |
| Empeorar una entrada nunca sube el índice | `test_score.py` |
| Los bloqueos **no** afectan al índice | `test_score.py` |
| El payload al tutor no contiene apps, dominios ni categorías | `test_intelligence.py` |
| El recorrido sólo usa información anterior a cada fecha | `test_intelligence.py` |
| Cargar dos veces el mismo fichero da el mismo frame | `test_metrics.py` |
| CLI y dashboard calculan lo mismo | `test_cli.py` |

---

## 4 · Decisiones que parecen arbitrarias y no lo son

Cada una está comentada en el sitio donde vive, y tiene test.

- **Contador de profundidad para la pantalla.** El log solapa sesiones y no dice
  qué apagado cierra qué encendido. La unión de tramos no depende de esa
  elección; cualquier emparejamiento sí, y se desvía en ambos sentidos.
- **Dos convenciones de día.** El día natural corta a medianoche (lo pide el
  enunciado); la noche va de las 23:00 a las 06:00 del día siguiente, porque el
  sueño no corta a medianoche.
- **Eje horario desplazado a las 04:00.** La madrugada se expresa como 24–28.
  Sin eso, la media de "hora de última pantalla" *baja* cuando alguien se
  acuesta más tarde.
- **Días truncados fuera.** Un día que el fichero sólo cubre en parte no entra
  en medias, rankings ni gráficos, pero sus eventos sí cuentan para la noche del
  día anterior.
- **Los cambios de app se reinician cada día**, o la primera app de la mañana
  cuenta como cambio respecto a la última de la noche.

---

## 5 · Cómo hacer los cambios más probables

### Añadir una métrica diaria

En `metrics.py`, dentro del `rows.append({...})` de `daily_frame`. Si es
derivable de columnas ya existentes, mejor calcularla en `add_score` o en la
capa que la use: `daily_frame` recorre eventos y debería quedarse con lo que
necesita ese recorrido.

### Añadir una regla de aviso

1. Escribe `_mi_regla(df) -> list[Signal]` en `intelligence.py`.
2. Añádela a `RULES`.
3. Ponle `actionability` con criterio: por debajo de 0,5 nunca se notifica, va
   a resumen semanal. Es la palanca con la que se decide qué merece interrumpir.
4. Añade el test que fija en qué fecha dispara y en cuál no.

### Añadir una regla de refuerzo

Igual, pero en `POSITIVE_RULES`, devolviendo con el helper `_pos(...)`. Tres
condiciones antes de escribirla:

- compara contra el **propio historial** del usuario, no contra un umbral fijo;
- exige margen (10 % en récords, 20–30 % en agregados semanales);
- el texto describe, no recomienda. Hay un test que caza los imperativos.

### Cambiar los pesos del índice

`COMPONENTS` en `score.py`. Los tests de acotación y monotonía no dependen de la
calibración, así que seguirán pasando; los de `test_data_contract.py` que citan
cifras concretas sí, y eso es a propósito: si una recalibración cambia lo que el
dashboard afirma, el test lo dice antes que el lector.

### Añadir un perfil

`PROFILES` en `run.py` y `HAS_GUARDIAN` en `app.py`. En producción esto vendría
de la cuenta; hoy son dos constantes porque hay dos ficheros.

---

## 6 · Límites conocidos

- **Un mes de datos.** Las reglas semanales necesitan 2–3 semanas de referencia,
  así que las dos primeras semanas de cualquier perfil nuevo no generan nada.
- **El detector de deriva usa referencia móvil**, así que deja de disparar
  cuando el comportamiento nuevo se convierte en el normal. Es lo correcto para
  avisar una vez, pero su silencio no significa "resuelto".
- **La madrugada del primer día del periodo** pertenece a una noche anterior al
  dato y no se contabiliza en ninguna fila.
- **La cobertura de atribución no llega al 100 %** (86 % en A, 67 % en B): el
  resto es pantalla de bloqueo, escritorio y notificaciones.
- **Todo cabe en memoria.** Con 11.488 eventos sobra; con un año de un millón de
  usuarios, `daily_frame` pasaría a un agregado incremental por día en el
  dispositivo, que es donde debería vivir de todas formas.

---

## 7 · Comandos

```bash
make install    # entorno + dependencias
make test       # 91 tests
make run        # análisis por consola
make json       # el mismo análisis en JSON
make csv        # frames diario y semanal a out/
make dash       # dashboard en http://localhost:8501
```
