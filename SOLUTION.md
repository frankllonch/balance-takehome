# Balance · take-home

Del log de eventos de un dispositivo a métricas, índice de bienestar, avisos al
tutor y refuerzos al usuario.

```bash
make install    # entorno y dependencias
make test       # 91 tests
make run        # análisis de los dos perfiles por consola
make dash       # dashboard
```

| Documento | Para qué |
|---|---|
| Este | qué encontré en los datos y por qué decidí lo que decidí |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | cómo está montado y cómo cambiarlo |
| [`SCHEMA.md`](SCHEMA.md) | formato de entrada (dado) |
| [`README.md`](README.md) | el enunciado (dado) |

Estado: las cuatro fases del enunciado están construidas, con CLI y 91 tests.
Lo que dejé fuera a propósito está en la sección 9 y lo que dejaría para una segunda vuelta en la 10.

---

## 1 · Qué hay en los datos

| | Usuario A | Usuario B |
|---|---|---|
| Eventos | 2.941 | 8.547 |
| Días completos | 30 (1–30 may) | 30 (1–30 may) + cola del 31 |
| Pantalla / día | 2 h 02 min | 4 h 22 min |
| Desbloqueos reales / día | 19 | 45 |
| Vistazos sin desbloquear / día | 4,4 | 4,4 |
| Apps distintas / día | 6,7 | 12,7 |
| Cambios de app / hora de pantalla | 9,4 | 16,8 |
| Offline en vigilia (07:00–23:00) | 14,0 h | 12,1 h |
| Pantalla 23:00–06:00 | **0,0 min los 30 días** | 30 min de media |
| Intentos bloqueados | 53 | 1.167 |
| De ellos ADULT / GAMBLING | 0 | 203 |
| Detección de desnudos en dispositivo | 0 | 43 |

**A es un adulto; B es un menor con tutor.** No lo dice el enunciado, lo dice el
comportamiento: B usa Duolingo y Kindle a diario, mantiene tres apps de
mensajería en paralelo, *intenta* abrir Roblox (75 veces, el filtro deja pasar 2)
y Clash of Clans (71 intentos, 0 pasan), y produce categorías `ADULT`/`GAMBLING`
que en A no aparecen ni una vez. Eso decide el resto del diseño: **para A el producto ya funciona y lo
correcto es callarse; para B hay una historia que contar, y hay que decidir qué
parte de ella le corresponde al tutor.**

## 2 · El hallazgo

El volumen de uso de B apenas cambia; su horario sí. Entre la semana 1 y la 4:

| | Semana 1 | Semana 4 | Δ |
|---|---|---|---|
| Pantalla / día | 244 min | 265 min | **+8 %** |
| Desbloqueos / día | 43 | 44 | +3 % |
| Minutos de madrugada | 4,4 | 59,2 | **×13** |
| Desbloqueos tras medianoche | 0,6 | 9,3 | **×16** |
| Última pantalla (media) | 23:21 | 01:06 | **+105 min** |
| Primer desbloqueo (media) | 08:43 | 08:54 | +10 min |
| Ventana de sueño | 9,4 h | 7,8 h | **−95 min** |

La hora de acostarse se retrasa 105 minutos y la de levantarse se mantiene, así
que el desplazamiento sale íntegro del tiempo de descanso disponible. Una regla
sobre tiempo de pantalla no habría detectado este caso: el volumen sube un 8 %
y la franja nocturna se multiplica por 13.

A registra **0,0 minutos** de pantalla
nocturna en 30 días. El umbral de las 23:00 no es un capricho del score: hay
gente que lo respeta sola, así que penalizarlo separa en vez de castigar a todos.

**Contenido sensible: pico, no tendencia.** Los 203 intentos de contenido adulto y apuestas
de B no son una tendencia, son un **pico**: 145 de los 203 (71 %) caen en las
semanas 2 y 3, y en la 4 bajan a 30. Y la persistencia es baja: agrupando en
ráfagas de 10 minutos salen **1,2 intentos de media, máximo 3**. Es alguien que
prueba, encuentra el bloqueo y abandona, no de insistencia sobre el mismo
contenido. Determina el destino de la señal: resumen semanal, no notificación.

**El filtro interviene cada vez menos en A.** Los bloqueos caen de 19 en la
semana 1 a 3 en la semana 4, y la cuota de distracción del 19 % al 15 %. El muro
interviene menos porque el hábito de apertura se ha desplazado, no porque la
barrera lo esté conteniendo más. El tiempo de pantalla de A es el mismo que el
primer día, así que esta señal no aparece en ninguna métrica de volumen.

**Reparto por categorías, sin diferencia relevante:** la cuota de distracción
media de B (17,5 %) es prácticamente la misma que la de A (15,5 %). El problema de B
no es el reparto por categorías, sino el volumen total, el horario y el número
de intentos bloqueados.

## 3 · Decisiones de ingeniería (el dato no viene limpio)

1. **Las sesiones de pantalla se solapan.** 77 `SCREEN_ON` en A y 411 en B
   ocurren con la pantalla ya encendida, compensados más tarde por `SCREEN_OFF`
   consecutivos. El dato no dice qué apagado cierra qué encendido, y elegir mal
   cambia el resultado **en las dos direcciones**. Sobre el usuario A:

   | Estrategia | Horas | Frente a la unión |
   |---|---|---|
   | Unión (contador de profundidad) | **61,1** | — |
   | Pila LIFO | 64,9 | +6 %, cuenta dos veces el solape |
   | Cola FIFO | 56,7 | −7 %, pierde el tramo sobrante |
   | Reiniciar el reloj en cada ON | 53,0 | −13 % |

   La pantalla se modela como contador de profundidad (ON suma, OFF resta;
   encendida mientras > 0), que devuelve la **unión** de los tramos. La unión no
   depende del emparejamiento elegido, y es lo que significa «la pantalla estuvo
   encendida». En B el abanico va de 93,4 h a 155,1 h frente a 131,1 de la
   unión.
2. **Días truncados por el borde del fichero.** B llega hasta las 00:46 del 31.
   Ese día se excluye de medias, rankings, mapa de calor y bloqueos; sus eventos
   sí cuentan para la noche del día 30. Sin el filtro, la media de pantalla de B
   baja de 261,8 a 253,7 min.
3. **Dos convenciones de día, a propósito.** El día natural corta a medianoche
   (lo pide el enunciado). La **noche** se mide 23:00 del día D → 06:00 del D+1,
   porque el sueño no corta a medianoche y partir una noche en dos filas destruye
   justo la señal que importa. Borde conocido: la madrugada del primer día del
   periodo pertenece a una noche anterior al dato y no se contabiliza.
4. **El "primer desbloqueo" necesita suelo.** Con corte a medianoche, un día que
   arranca a las 00:20 (cola de la noche anterior) se registra como "empezó el
   día a las 00:20". Se define como el primero **a partir de las 06:00**.
5. **Tiempo por dominio, no por navegador.** Un `URL_VISIT` le quita el tiempo a
   Chrome y se lo queda el dominio. Por eso Chrome aparece con 115 aperturas y
   12 minutos en A: es un contenedor, no un destino.
6. **Pickup real vs vistazo:** `SCREEN_ON` con un `USER_PRESENT` antes del
   siguiente ON/OFF. A: 573 pickups / 133 vistazos sobre 706 `SCREEN_ON`.
   B: 1.349 / 131 sobre 1.480.
7. **Los cambios de app se reinician cada día.** Sin eso, la primera app de la
   mañana cuenta como cambio respecto a la última de la noche anterior: 0,83
   cambios falsos al día en los dos perfiles (4,1 % del total en A, 1,1 % en B).
8. **Guardas que no llegan a activarse con estos ficheros:** eventos con la
   pantalla apagada, `USER_PRESENT` huérfano y el tope de 45 min de primer
   plano (el tramo más largo observado es de 32,6 min). Están en el código
   porque un dispositivo real sí los produce. La única anomalía que aparece son
   4 `USER_PRESENT` duplicados dentro de un tramo en A y 6 en B.

Cobertura: se atribuye a app o sitio el **86 %** del tiempo de pantalla de A y
el **67 %** del de B. El resto es pantalla de bloqueo, escritorio y
notificaciones, y que en B sea menor es coherente con su patrón de picoteo.

## 4 · El índice de bienestar (0–100)

| Componente | 100 con | 0 con | Peso |
|---|---|---|---|
| Tiempo de pantalla | ≤ 90 min | ≥ 360 min | 25 % |
| Fragmentación (desbloqueos) | ≤ 15 | ≥ 60 | 20 % |
| Noche protegida (min 23:00–06:00) | 0 | ≥ 60 | 20 % |
| Desconexión más larga en vigilia | ≥ 4 h | ≤ 1 h | 15 % |
| Intención (cuota de distracción) | ≤ 10 % | ≥ 50 % | 20 % |

Resultado: **A 83** (82 → 82 entre la semana 1 y la 4), **B 48** (60 → 41, arrastrado por la noche).

**Anclaje absoluto, narrativa personal.** El número se mide contra bandas fijas;
la comparación con uno mismo (mediana móvil de 14 días) va *al lado*, no dentro.
Si el score fuera relativo, quien lleva 6 h/día constantes sacaría 100 por ser
constante.

**Los bloqueos no puntúan, a propósito.** Un `BLOCK` significa que el teléfono
hizo su trabajo y el contenido no se abrió. Penalizar el intento castiga a
alguien por un impulso que el producto ya resolvió, y crea el incentivo de
desactivar la protección para subir nota.

**Por qué la noche pesa 20 % siendo la métrica más pequeña.** 60 minutos a la
01:00 y 60 a las 17:00 no cuestan lo mismo, y es la palanca más barata: pedir
dos horas menos al día es pedir un cambio de vida; pedir soltarlo 40 minutos
antes es pedir una cosa.

### Dónde se rompe

- **Bandas iguales para todos.** Un adolescente y un adulto que teletrabaja no
  deberían medirse igual. Con más tiempo: calibrar por cohorte, o cambiar a
  percentil personal después de 30 días de baseline.
- **Castiga al usuario legítimamente intensivo.** Alguien que usa el móvil para
  trabajar sale mal sin hacer nada mal. Falta una noción de "uso con propósito".
- **La cuota de distracción sólo ve lo que sí se abrió.** Las categorías más
  problemáticas de B no aparecen en su mix porque el teléfono nunca las dejó
  abrirse: el score de intención de B sale artificialmente bueno (81/100).
- **Un solo número esconde la varianza.** B y alguien con la misma media pero
  todo concentrado en dos atracones sacan lo mismo.
- **Es gamificable**: apagar la pantalla y volver a encenderla no cambia nada,
  pero un usuario decidido puede optimizar la métrica sin cambiar el hábito.

## 5 · Alertas y nudges (`balance/intelligence.py`)

### La alerta al tutor: cambio de régimen, no umbral

Tres reglas corren sobre el mes. La tercera está a propósito como **control
negativo**:

| Regla | Qué mira | ¿Dispara? |
|---|---|---|
| `night_drift` | mediana de 5 noches contra las 14 anteriores, más el retraso de la hora de apagar | **B: 19 may**. A: nunca |
| `sensitive_spike` | intentos sensibles de 7 días contra el ritmo previo | B: 14 may. A: nunca |
| `screen_jump` | «el tiempo de pantalla ha subido mucho» | **nunca, en ninguno de los dos** |

`screen_jump` es la regla de volumen convencional y no se activa en ninguno de
los dos perfiles: el uso diario de B sube un 8 % en el mes mientras su horario
nocturno se multiplica por 13. Sirve como control, y confirma que la detección
de este caso depende de vigilar el horario, no el total.

`night_drift` se activa el **19 de mayo**, doce días antes del final del fichero
y antes de que ninguna métrica de volumen dé señal. Deja de cumplirse el 23
porque la referencia móvil de 14 días incorpora el comportamiento nuevo. Para
avisar es el comportamiento correcto (se notifica el cambio una vez), pero
implica que **el silencio del detector no equivale a "resuelto"**. El nivel
absoluto lo siguen reflejando el índice y el resumen semanal, que no usan
referencia móvil.

### El presupuesto de silencio

El riesgo principal de un canal de avisos a un tutor es la saturación: un canal
que notifica de más deja de leerse. Hay **cupo de 2 avisos por 30 días** y
separación mínima de 10 días, y cada candidata se ordena por
`magnitud × persistencia × accionabilidad` (producto, no suma: algo enorme de un
día, o persistente pero sobre lo que no se puede actuar, no debe colarse).

En B, `sensitive_spike` **se detecta y no se envía**. Su accionabilidad es 0,35
a propósito: el teléfono ya bloqueó los 203 intentos, ninguno se abrió, y la
conversación que queda no gana nada por llegar hoy en vez del domingo. Baja a
resumen semanal.

El dashboard lista las señales retenidas con su motivo, en «Alertas y nudges».

### El nudge, medido antes de enviarlo

Regla: segunda reapertura a partir de las 23:30, una vez por noche. Silencios:
una sola reapertura no es un patrón; y si las últimas noches ya van mejor que su
propia media, callarse.

No se puede hacer A/B sobre un fichero cerrado, pero sí **reproducir la regla
sobre el historial**:

| | Usuario A | Usuario B |
|---|---|---|
| Noches con aviso | **0 de 30** | 14 de 30 (47 %) |
| Min nocturnos del mes | 0 | 905 |
| Min posteriores al disparo | 0 | **348 (38 %)** |
| Por noche con aviso | n/a | ~25 min |

348 minutos es el máximo teórico recuperable, no el efecto esperado; acota si
la regla apunta a algo con margen antes de gastar una interrupción en ella. La
tasa de activación en A es del 0 % sin configuración específica por perfil.

### Contexto, no sólo cifras

El enunciado pide que un número signifique algo, con un ejemplo concreto: «30
minutos menos de lo normal en ti, y tu racha más larga fue el sábado por la
tarde». La comparación con uno mismo estaba desde el principio (mediana móvil de
14 días); el **cuándo** de la racha faltaba, y se calculaba la duración sin
guardar el momento. Ahora `longest_offline_when` da la frase («el sábado al
mediodía») y aparece en el ritmo diario, en el resumen semanal y en el detalle
del día.

### Recorrido del mes (cómo se demuestra que funciona)

La pestaña «Alertas y nudges» abre con un recorrido deslizable: **un solo
gráfico con las siete variables que leen las reglas**, encendibles y apagables
desde la leyenda, sobre la misma línea de tiempo en la que van marcados los
avisos, los refuerzos y los nudges.

Siete magnitudes en un eje exigen una transformada común. Cada serie va como
**porcentaje de su propio máximo del periodo**: no es una escala doble
disfrazada, es una única escala con una transformada declarada, y el valor real
con su unidad viaja en el tooltip. Se divide por el máximo y no se reescala a
min-max porque el cero tiene que seguir siendo el cero: en el usuario A, «cero
minutos de madrugada» es el dato, y min-max lo pintaría a media altura.

Arrancan tres series encendidas (madrugada, última pantalla y pantalla al día) y
las otras cuatro entran con un clic. La leyenda va agrupada en «Variables
vigiladas» y «Emisiones», pero con `groupclick="toggleitem"`: el grupo es sólo
un título, y cada entrada se enciende y se apaga por su cuenta. Con el
comportamiento por defecto de Plotly, un clic habría apagado el grupo entero. Siete líneas a la vez se leen mal, y
empezar con todas obliga al lector a apagar en vez de a encender. Cada serie
lleva además su propio patrón de trazo: la validación de la paleta deja el peor
par adyacente en ΔE 10,3 sobre fondo oscuro, dentro de la banda que exige una
codificación secundaria, y el trazo es esa codificación.

Debajo del cero hay un **carril de eventos** con lo que el teléfono emitió cada
día, con un símbolo por tipo. También se enciende y se apaga desde la leyenda, y
comparte eje temporal con los datos que lo explican: se ve el aviso del 19 de
mayo justo encima de la subida de la madrugada que lo provoca.

Debajo, las salidas de esa fecha. **Sólo se dibujan las que existen**: si no hay
notificación sale un hueco que pone «sin notificaciones», y la columna del tutor
no aparece en perfiles sin tutor. Un teléfono dibujado diciendo «no se muestra
nada» es una notificación que anuncia que no hay notificación: ocupa lo mismo y
pesa lo mismo que las que sí importan.

Las reglas se **reevalúan con el histórico disponible hasta esa fecha**, no con
el mes completo (`month_replay`): el teléfono del día 12 no sabía lo que iba a
pasar el 19, y el recorrido tampoco. Moviendo el control se ve el sistema
callado hasta el 10 de mayo, el primer nudge esa noche, la entrada de resumen
semanal el 14 y la notificación al tutor el 19.

Cierra con la lista completa de emisiones del mes:

| Destino | Usuario A | Usuario B |
|---|---|---|
| Nudge en pantalla | 0 | 14 |
| Refuerzo al usuario | 3 | 1 |
| Notificación al tutor | sin tutor | 1 |
| Refuerzo al tutor | sin tutor | 1 |
| Entrada de resumen semanal | sin tutor | 1 |
| **Total en 30 días** | **3** | **18** |

Es la forma más directa de enseñar las dos funciones que pide el enunciado
juntas y en contexto: una va al tutor y otra al usuario, con datos distintos,
en el mismo instante y a partir del mismo stream.

### La privacidad, dibujada

En «Salidas del día» se ve, en la misma fecha, la pantalla del usuario (detalle
completo, en el dispositivo) al lado de la tarjeta del tutor (agregado grueso,
redondeado a cuartos de hora y múltiplos de 5).

Un valor fino («247 minutos, índice 41,3») identifica a un usuario concreto y,
en serie de 30 días, permite reconstruir buena parte del comportamiento. A la
granularidad que se transmite, el tutor distingue igual de bien las dos cosas
que necesita saber (si el estado es normal y si ha cambiado).


## 6 · Refuerzo positivo

Un sistema que sólo habla cuando algo empeora se lee como una amenaza, y el
usuario A lo demuestra: con las reglas de aviso solas, un perfil sano recibe
**cero** información sobre su propio uso en 30 días.

### Criterios

Tres reglas de diseño antes de las seis reglas de detección:

1. **Contra uno mismo, no contra una tabla.** Un umbral absoluto felicita
   siempre al usuario A y nunca al B, que es exactamente al revés de lo que
   sirve. Todo se compara con las propias semanas anteriores de esa persona.
2. **Sólo con margen.** 10 % sobre el mejor registro reciente en récords, 30 %
   en agregados semanales. Un récord batido por un minuto es varianza.
3. **Descriptivo, nunca prescriptivo.** El texto dice qué ha pasado y contra
   qué se compara. No felicita en segunda persona ni sugiere qué hacer después.

| Regla | Qué mide | Umbral | Destino |
|---|---|---|---|
| `offline_record` | mejor rato seguido sin pantalla | supera en 10 % el mejor de los 14 días previos, mínimo 3 h | usuario |
| `night_streak` | noches seguidas sin pantalla de 23:00 a 06:00 | hitos en 7, 14 y 30 | usuario |
| `calm_week` | veces al día que interviene el filtro | 30 % por debajo de las dos semanas anteriores | usuario |
| `focus_week` | cuota de tiempo en redes, ocio y juegos | 20 % por debajo de la semana anterior | usuario |
| `best_week` | índice semanal | máximo del historial, con 3 semanas previas | usuario |
| `filter_calm` | intentos hacia contenido sensible | 40 % por debajo de la semana anterior, partiendo de 10 o más | tutor |

Cupo: **un refuerzo por semana y audiencia**. Lo que no entra no se descarta,
baja al resumen semanal.

### Qué dispara con estos datos

| | Usuario A | Usuario B |
|---|---|---|
| Refuerzos al usuario | 3 (7, 14 y 28 may) | 1 (28 may) |
| Refuerzos al tutor | sin tutor | 1 (28 may) |
| Registrados sin notificar | 3 | 0 |
| Avisos | 0 | 1 |

**A** recibe los hitos de 7 y 14 noches protegidas y la semana en que el filtro
pasa de 2,1 a 0,4 intervenciones diarias. Uno cada diez días de media.

**B** recibe uno: la semana 4 baja su cuota de distracción del 20 % al 16 %. Y
su tutor recibe `filter_calm`, porque los intentos sensibles caen de 73 a 30
entre la semana 3 y la 4. Ese es el punto: el tutor de B recibe **un aviso y un
refuerzo** en el mismo mes, no sólo malas noticias.

`best_week` y `offline_record` disparan en A pero caen al resumen por cupo, que
es la prueba de que el presupuesto hace algo.

### Semanas incompletas

Ninguna regla semanal evalúa semanas de menos de 5 días. La semana 5 del
periodo tiene 2 o 3 días y saldría artificialmente buena en casi todo; el
resumen semanal la marca con asterisco y avisa de que la comparación es menos
fiable.

## 7 · Resumen semanal

Pestaña propia, con selector de semana y de perfil. Reutiliza las métricas que
ya existen agregadas por semana: KPIs con variación frente a la semana
anterior, evolución semana a semana de las cuatro magnitudes principales, los
cinco componentes del índice, el detalle de los días de esa semana contra la
media de las anteriores, una tabla de comparación y todo lo que el teléfono
emitió esos días.

La variación se calcula **redondeando antes de restar**, para que la columna
cuadre con las dos que tiene al lado; y cuando el cambio redondea a cero se
escribe «sin cambio» en vez de «+0», que con flecha verde diría que algo ha
mejorado cuando no se ha movido.


## 8 · La línea de privacidad, en concreto

- Las pestañas *En qué se va el tiempo* y *Lo que el teléfono paró* son vista
  **del propio usuario, en el dispositivo**. Nunca salen.
- Al tutor le llegaría el agregado sin objeto y sin conteo fino: *"esta semana
  el filtro de contenido sensible ha actuado más de lo habitual; puede ser buen
  momento para hablar"*, nunca *"tu hijo intentó abrir pornhub.com 31 veces"*.
- Lo que sí es tranquilizador y sí se puede decir: **203 intentos sensibles,
  0 abiertos**. Verificado en el stream: no hay ni un solo `URL_VISIT` o
  `APP_FOREGROUND` con categoría `ADULT` o `GAMBLING` en ninguno de los dos
  ficheros. El bloqueo es efectivo al 100 %.

## 9 · Lo que dejé fuera a propósito

No es lo mismo que "lo que falta". Estas cinco cosas se podían hacer y decidí
no hacerlas:

- **Un score relativo al propio usuario.** Sería más amable y menos comparable.
  Alguien con 6 h/día constantes sacaría 100 por ser constante, y el número
  dejaría de significar nada. La comparación personal va *al lado* del índice,
  no dentro.
- **Penalizar los bloqueos en el índice.** Habría sido la decisión fácil y
  habría separado mejor a los dos usuarios. Crea el incentivo de desactivar la
  protección para subir nota, así que no entra.
- **Notificar el pico de contenido sensible.** Se detecta y se retiene: el
  filtro ya lo paró, la persistencia es de 1,2 intentos por ráfaga y la
  conversación que queda no mejora por llegar hoy. Va al resumen semanal.
- **Rankings de apps y dominios para el tutor.** Son la parte más vistosa del
  análisis y la que rompe la línea de privacidad. Se quedan en el dispositivo.
- **Nudges de tiempo de pantalla.** Interrumpir a alguien porque lleva tres
  horas de móvil no cambia nada y gasta atención. El único nudge implementado
  ataca el horario, que es donde hay margen medible.

## 10 · Lo que falta y cómo lo haría

**Una rebanada de Django.** Ellos usan Django. `balance/` ya es una librería
pura sin framework, y Streamlit y el CLI son dos adaptadores sobre ella, así que
Django sería un tercero. Lo que haría distinto es convertir la línea de
privacidad en un contrato que el código impone: dos serializers
(`DeviceSerializer` / `GuardianSerializer`) y el test de no-inversión, que en
esta entrega vive en `test_intelligence.py` y allí sería una prueba de la API.

**Calibrar por cohorte.** Hoy las bandas del índice y los umbrales de las reglas
son iguales para un adulto que teletrabaja y para un adolescente. Con más datos
se calibran por cohorte, o se pasa a percentil personal tras 30 días de
referencia.

**Detectar atracones.** La media esconde la varianza: alguien con la misma media
que B pero concentrada en dos noches saca el mismo índice. Percentil 95 de
duración de sesión.

**Decaimiento de intervención.** Los bloqueos de A caen de 19 a 3 por semana.
No es una métrica del usuario, es la métrica de negocio de Balance: con qué
velocidad el teléfono deja de tener que intervenir. Está en los datos y en el
CLI, pero no tiene vista propia.

**Cálculo incremental.** Hoy todo se recalcula desde el log entero en cada
ejecución, que con 11.488 eventos sobra y además hace el resultado trivialmente
reproducible. Con volumen real, `daily_frame` pasaría a un agregado incremental
por día calculado en el dispositivo, que es donde debería vivir de todas formas.

## 11 · Estructura

```
balance/events.py        eventos crudos → intervalos, usos y bloqueos
balance/metrics.py       Timeline → frame diario y semanal
balance/score.py         frame diario → índice 0–100 + descomposición
balance/intelligence.py  frame diario → avisos con cupo, refuerzos, nudge y recorrido
balance/run.py           CLI (texto, JSON, CSV)
balance/charts.py        figuras plotly · no deciden nada
balance/theme.py         tema oscuro, paleta validada, maqueta de dispositivo
app.py                   dashboard streamlit (8 pestañas)
tests/                   91 tests · capas 0 a 4, CLI y contrato de datos
```

`events`, `metrics`, `score`, `intelligence` y `run` no importan Streamlit ni
Plotly: el núcleo se puede calcular, probar y programar en un `cron` sin la
interfaz. Los detalles de cómo cambiar cada pieza están en
[`ARCHITECTURE.md`](ARCHITECTURE.md).

## 12 · Sobre la verificación

El dashboard afirma cosas («77 solapes», «el filtro de A cae de 19 a 3», «203
intentos sensibles y ninguno abierto»). Cada una de esas afirmaciones tiene un
test en `tests/test_data_contract.py` que la recalcula por un camino distinto.

No es decorativo: escribir esos tests destapó **cuatro cifras publicadas que
estaban mal**, todas heredadas de código exploratorio que usaba un modelo de
pantalla booleano en vez del contador de profundidad que implementa el código.
Están corregidas; el detalle está en la sección 3.
