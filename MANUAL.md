# FrED-LANG — Manual del Proyecto
## Capa de Control del Robot

> Documento de referencia técnica de la capa de control del brazo robótico
> UFACTORY xArm6 para el proyecto FrED-LANG.
>
> Última actualización: 2026-09-13

---

## Índice

1. [Introducción](#1-introducción)
2. [Visión general del sistema](#2-visión-general-del-sistema)
3. [Entorno de desarrollo](#3-entorno-de-desarrollo)
4. [La librería `FredArm`](#4-la-librería-fredarm)
5. [Notas de ingeniería](#5-notas-de-ingeniería)
6. [Guía de uso — ejemplos](#6-guía-de-uso--ejemplos)
7. [Trabajo futuro](#7-trabajo-futuro)
8. [Referencias](#8-referencias)

---

## 1. Introducción

<!-- PENDIENTE -->

---

## 2. Visión general del sistema

<!-- PENDIENTE -->

---

## 3. Entorno de desarrollo

<!-- PENDIENTE -->

---

## 4. La librería `FredArm`

<!-- ============================================================
     SECCIÓN EN CONSTRUCCIÓN — empezamos por aquí
     ============================================================ -->

### 4.1 Arquitectura en capas

`FredArm` está organizada como una **jerarquía de abstracción**: cada capa usa la de
abajo y esconde su complejidad. El código de más alto nivel (y en el futuro, el generado
por el LLM) trabaja con verbos semánticos, sin preocuparse por los detalles de los
servicios ROS2 subyacentes.

```
┌───────────────────────────────────────────────────────────────────────┐
│  Capa 3 — Primitivas de alto nivel        home()  mover_a()  agarrar()  │  (en construcción)
│           (verbos semánticos)                                          │
├───────────────────────────────────────────────────────────────────────┤
│  Capa 2 — Lectura y verificación de       esperar_listo()  hay_error() │
│           estado                          servos_ok()  get_angulos()   │
├───────────────────────────────────────────────────────────────────────┤
│  Capa 1 — Cliente de servicios /xarm/*    motion_enable()  set_mode()  │
│           (control de bajo nivel)         set_state()  set_position()  │
│                                           set_servo_angle()            │
│                                           move_gohome()  clean_error() │
├───────────────────────────────────────────────────────────────────────┤
│  Capa 0 — Driver xarm_api (C++) + ROS2    servicios y tópicos /xarm/*  │
└───────────────────────────────────────────────────────────────────────┘
```

Organizar la clase `FredArm` en estas capas asegura que el LLM que controlará el xArm
tenga todo lo necesario para moverlo, y a la vez disponga de herramientas de alto nivel
que faciliten el uso de la librería. El objetivo del proyecto es traducir lenguaje natural
a código Python, y para un LLM es mucho más sencillo convertir una instrucción como
*"mueve la pieza roja de la posición A a la posición B"* en código que usa verbos
semánticos:

```python
agarrar()
mover_a(...)
soltar()
```

...que en código que orquesta directamente los servicios de bajo nivel del firmware:

```python
motion_enable()
set_mode()
set_state()
set_position(...)
```

Esta separación da una doble ventaja. Por un lado, las primitivas de alto nivel encapsulan
secuencias ya validadas: el LLM no puede equivocarse en *cómo* se ejecuta un movimiento,
solo en *cuándo* — lo que reduce la superficie de error y refuerza el principio de
**seguridad** del proyecto. Por otro, un script escrito con estos verbos se lee como una
receta, lo que sostiene el principio de **interpretabilidad**: cualquiera puede auditar qué
hará el robot sin descifrar llamadas de bajo nivel.

Al mismo tiempo, mantener expuesta la Capa 1 conserva el acceso directo a los servicios del
firmware para casos que las primitivas no cubran (depuración, movimientos especiales,
control fino). La librería se diseñó contemplando ambos escenarios: facilitar el trabajo
del LLM sin sacrificar el control de bajo nivel.

> **Nota:** la separación en capas es *conceptual*, no física. Todos los métodos viven en
> la misma clase `FredArm`; las capas describen niveles de abstracción, no clases o
> archivos distintos.

### 4.2 Anatomía de un método

Todos los métodos que llaman a un servicio siguen el mismo patrón (el "molde"):

```
1. Construir el request         request = TipoServicio.Request()
2. Llenar sus campos            request.campo = valor
3. Enviar de forma asíncrona    future = cliente.call_async(request)
4. Esperar la respuesta         rclpy.spin_until_future_complete(self, future)
5. Leer el resultado            return future.result().ret
```

En el sistema de servicios de ROS2, las llamadas y sus respuestas no llegan al instante:
los procesos que emplean parte de las funciones de `FredArm` son **asíncronos**. Cuando
usamos `call_async`, este no nos devuelve la respuesta que esperamos, sino un **`future`**
— que en términos simples es una promesa de que llegará un resultado más adelante.

Por eso necesitamos `spin_until_future_complete`: este corre el executor de ROS2 hasta que
ese `future` se completa, y solo entonces nos devuelve el control. Es el **puente** entre
los procesos asíncronos de ROS2 y una API síncrona cómoda de usar, como la que exponemos
en nuestro código:

```python
ret = arm.set_mode(0)
```

Desde el punto de vista de quien llama, esa línea se comporta como una función normal:
bloquea hasta tener el resultado y devuelve el `ret` directamente. Toda la complejidad
asíncrona queda encapsulada dentro del método, de modo que las capas superiores —y el
LLM— pueden encadenar comandos sin lidiar con `future`s ni con el executor.

### 4.3 Referencia de la API — Capa 1

Referencia de los métodos de bajo nivel de `FredArm`. Cada uno es un cliente de un
servicio `/xarm/*` (salvo los de lectura de estado, que leen del tópico
`/xarm/robot_states`).

#### Arranque

Estos tres métodos deben llamarse **en orden** para dejar el brazo listo para moverse:
`motion_enable → set_mode → set_state`.

**`motion_enable(enable, id=8)`**
Habilita o deshabilita los servomotores del brazo. Debe llamarse antes de `set_mode` y
`set_state`.
- `enable` (int): `1` = habilitar, `0` = deshabilitar.
- `id` (int): servo objetivo. `1`–`6` para un eje individual, `8` = todos los ejes (default).
- **Retorna** (int): `ret` del driver. `0` = éxito.
- **Nota:** contra el firmware simulado devuelve `ret=3` (timeout cosmético), pero los
  servos sí se habilitan. Verificar con `servos_ok()` / `mt_able` en `/xarm/robot_states`.

**`set_mode(mode)`**
Fija el modo de operación del brazo. Debe fijarse con el brazo en STOP/STANDBY, antes de
`set_state(0)`.
- `mode` (int): modo de control. `0` = posición punto a punto (el usado en el flujo
  actual). Otros: `1` = servoj, `2` = manual/Free-Drive, `4`/`5` = velocidad
  articular/cartesiana, `6`/`7` = replanning online.
- **Retorna** (int): `ret` del driver. `0` = éxito.

**`set_state(state)`**
Fija el estado del brazo. Llamar con `0` al final del arranque para dejarlo listo.
- `state` (int): `0` = STANDBY (listo, además limpia errores; el feedback pasa a `2`),
  `3` = PAUSED, `4` = STOP.
- **Retorna** (int): `ret` del driver. `0` = éxito.
- **Nota:** los estados que se *fijan* no coinciden con los que se *leen* en
  `/xarm/robot_states` (ver [4.4](#estados-fijados-vs-estados-leídos)).

#### Movimiento

Requieren modo `0` y estado READY. Todos aceptan `wait` (bloquear hasta terminar) y
devuelven `ret`.

**`set_position(pose, speed=200.0, acc=2000.0, wait=True)`**
Movimiento en **espacio cartesiano**: se especifica la pose del efector final (TCP) y el
firmware resuelve la cinemática inversa.
- `pose` (list[float]): `[x, y, z, roll, pitch, yaw]`. **XYZ en mm, orientación en radianes.**
- `speed` (float): velocidad lineal del TCP, en mm/s.
- `acc` (float): aceleración lineal del TCP, en mm/s².
- `wait` (bool): si `True`, bloquea hasta terminar el movimiento.
- **Retorna** (int): `ret` del driver. `0` = éxito.
- **Nota:** con `motion_type=0` (default) el movimiento es lineal; si la pose no es
  alcanzable en línea recta, falla con error C40.

**`set_servo_angle(angles, speed=0.35, acc=10.0, wait=True)`**
Movimiento en **espacio articular**: se especifica el ángulo de cada junta directamente
(sin cinemática inversa).
- `angles` (list[float]): ángulo objetivo por junta, **en radianes**. Para xArm6 → 6 valores.
- `speed` (float): velocidad articular, en rad/s.
- `acc` (float): aceleración articular, en rad/s².
- `wait` (bool): si `True`, bloquea hasta terminar.
- **Retorna** (int): `ret` del driver. `0` = éxito.

**`move_gohome(speed=0.35, acc=10.0, wait=True)`**
Lleva el brazo a su pose home de fábrica (definida por el firmware). A diferencia de
`set_servo_angle([0,...])`, usa el home del fabricante.
- `speed` (float): velocidad articular, en rad/s.
- `acc` (float): aceleración articular, en rad/s².
- `wait` (bool): si `True`, bloquea hasta terminar.
- **Retorna** (int): `ret` del driver. `0` = éxito.

#### Lectura de estado

`FredArm` se suscribe a `/xarm/robot_states` y guarda el último mensaje en `_last_state`.
Estos métodos lo consultan (no llaman a ningún servicio).

**`hay_error()`**
- **Retorna** (bool): `True` si el brazo reporta un código de error (`err != 0`). `False`
  si no hay error o si aún no ha llegado ningún estado.

**`servos_ok(num_joints=6)`**
Verifica que los servos estén habilitados mediante el bitmask `mt_able`.
- `num_joints` (int): número de articulaciones a verificar (default `6`).
- **Retorna** (bool): `True` si las primeras `num_joints` juntas están habilitadas.

**`esperar_listo(timeout=10.0)`**
Bloquea (haciendo `spin_once`) hasta que el brazo esté en READY (`state=2`), sin error y
con los servos habilitados. Es la verificación que se llama tras cada comando para
confirmar que terminó bien.
- `timeout` (float): tiempo máximo de espera, en segundos.
- **Retorna** (bool): `True` si el brazo llegó a estado listo; `False` si hubo error o se
  agotó el tiempo.

**`get_angulos()`**
- **Retorna** (list[float] | None): ángulos articulares actuales (en radianes), o `None`
  si aún no ha llegado ningún estado.

#### Recuperación

**`clean_error()`**
Limpia el código de error del brazo. Tras limpiar, hay que volver a `set_state(0)` para
reactivar el movimiento.
- **Retorna** (int): `ret` del driver. `0` = éxito.

### 4.4 Conceptos clave

Cuatro conceptos que hay que entender para usar la librería correctamente y evitar los
errores más comunes.

#### Espacio articular vs. espacio cartesiano

Un brazo robótico físicamente solo sabe hacer una cosa: mover los motores de sus juntas a
ciertos ángulos. Un xArm6 tiene 6 juntas, es decir, 6 ángulos. Sobre esa base existen dos
formas de comandar un movimiento:

**Espacio articular (joint space)** — se le dan los 6 ángulos directamente
(`set_servo_angle`). El brazo mueve cada motor a su ángulo, sin cálculos intermedios. Es
predecible y sin ambigüedad: un conjunto de ángulos corresponde a una única configuración
física. Su desventaja es que resulta antinatural para tareas: nadie sabe de memoria qué
ángulos ponen la punta sobre un objeto.

**Espacio cartesiano (Cartesian space)** — se le da la pose deseada del efector final
(TCP): posición XYZ más orientación (`set_position`). El brazo resuelve por **cinemática
inversa** qué ángulos producen esa pose. Es la forma natural de pensar una tarea ("ve a
estas coordenadas"), a costa de que el firmware debe resolver la IK, con sus sutilezas:
puede haber varias soluciones, ninguna (fuera de alcance), o pasar por una singularidad.

En este proyecto el flujo principal es **cartesiano**, porque una cámara percibe el mundo
en coordenadas, no en ángulos — lo que se alinea con el futuro modelo VLA. El espacio
articular se reserva para poses fijas conocidas, como el home, donde guardar los ángulos
evita recalcular la cinemática inversa cada vez.

#### La máquina de estados y modos del xArm

El brazo tiene un **modo** (qué tipo de control acepta) y un **estado** (en qué situación
de ejecución está). Ambos se leen en `/xarm/robot_states`.

Modos (`mode`):

| Valor | Significado |
|---|---|
| 0 | Posición — control punto a punto (el usado en este proyecto) |
| 1 | Servoj — planificador de trayectoria externo |
| 2 | Teaching / Free-Drive — gravedad compensada |
| 4 / 5 | Control de velocidad articular / cartesiana |
| 6 / 7 | Replanning dinámico online (articular / cartesiano) |

Estados (`state`):

| Valor | Significado |
|---|---|
| 1 | RUNNING — ejecutando un comando de movimiento |
| 2 | SLEEPING — sin ejecución, listo para moverse (READY) |
| 3 | PAUSED — pausado a mitad de un movimiento |
| 4 | STOPPED — no listo para comandos |
| 5 | CONFIG_CHANGED — cambió configuración o modo, no listo |

Al arrancar en frío, el brazo suele reportar `state=5`. La secuencia de arranque
(`motion_enable → set_mode → set_state(0)`) lo lleva a READY.

#### Estados fijados vs. estados leídos

Un punto que causa confusión: **los valores de estado que se *fijan* con `set_state` no son
los mismos que se *leen* en `/xarm/robot_states`.** Son dos tablas distintas.

Cuando se llama `set_state(0)` (STANDBY), el feedback del robot **no** reporta `0` —
reporta `state=2` (READY). Es el comportamiento esperado: `set_state(0)` significa "ponte
listo", y el estado leído que corresponde a "listo" es el `2`. Además, `set_state(0)`
limpia el código de error de forma implícita.

Por eso `esperar_listo()` compara contra `state == 2` (el valor *leído*), no contra el `0`
que se fijó.

#### Unidades

Las unidades son la fuente de error más común. La regla:

- **Ángulos** (`set_servo_angle`): siempre en **radianes**. Nunca grados. Enviar `90`
  pensando en grados equivale a 90 radianes. Lo mismo pasa con los campos de velocidad
  `speed` y `acc`, estas tienen unidades de rad/s y rad/s² respectivamente.
- **Pose** (`set_position`): es una lista `[x, y, z, roll, pitch, yaw]` con **unidades
  mixtas** — posición (`x, y, z`) en **milímetros**, orientación (`roll, pitch, yaw`) en
  **radianes**. Por ejemplo, en `[300, 0, 250, 3.14, 0, 0]`, los primeros tres valores son
  mm y el `3.14` es π radianes (punta apuntando hacia abajo). Cuando utilizamos el modo de
  control cartesiano la velocidad y la aceleración (`speed` y `acc`) tienen unidades de
  mm/s y mm/s² respectivamente.

---

## 5. Notas de ingeniería

<!-- PENDIENTE -->

---

## 6. Guía de uso — ejemplos

<!-- PENDIENTE -->

---

## 7. Trabajo futuro

<!-- PENDIENTE -->

---

## 8. Referencias

<!-- PENDIENTE -->
