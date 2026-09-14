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

### 1.1 Qué es FrED-LANG

La meta con la que se creó el proyecto es construir un sistema que sirva como predecesor de
un VLA (Vision-Language-Action), y que a la vez facilite la interacción humano-robot. Hoy en
día, controlar un robot exige experiencia técnica; lo que este proyecto propone es que
controlarlo mediante lenguaje natural sea posible, usando un LLM como intérprete.

Este repositorio contiene la **capa de infraestructura ROS2** y el gemelo digital: el
entorno reproducible, el driver del robot y la librería de control (`FredArm`) sobre la que
se construyen las primitivas de alto nivel.

**Pipeline del sistema:**

```
   Persona            LLM              Python           ROS2            xArm6
  "agarra la    →   traduce a     →   primitivas   →  validación  →   ejecución
  pieza roja"      código Python     de movimiento    de seguridad    en el robot
```

**Principios de diseño:**

- **Seguridad** — ROS2 bloquea trayectorias imposibles antes de mover el brazo. Cero choques.
- **Interpretabilidad** — no es una "caja negra": si algo falla, el script de Python
  generado es legible y auditable.

La visión a largo plazo es usar este pipeline como generador de datos para entrenar un
modelo Vision-Language-Action (VLA) end-to-end.

### 1.2 Propósito del manual

Este manual tiene una tarea simple: documentar todo lo que se hizo durante la construcción de
la infraestructura que se utiliza dentro del proyecto. El documento servirá tanto al autor
como a los futuros ingenieros que trabajen sobre el sistema y el entorno que se ha construido
para cumplir con el objetivo del proyecto.

Aquí se explica cómo funciona la capa de control, cómo utilizarla y por qué se tomaron las
decisiones que se tomaron en su momento. De esta manera, cuando alguien quiera incorporarse
al proyecto, tendrá una guía para entender cómo se estructuró todo y por qué se estructuró
así. Este proyecto tiene una meta ambiciosa, mas no imposible; por eso es importante
documentar todo lo ocurrido, para que cuando se escale se haga de forma ordenada y consciente
de toda la estructura del sistema.

### 1.3 Alcance

El proyecto sigue en desarrollo, por lo que este manual no está completo. Todavía no
documenta la integración del entorno creado en ROS2 con el LLM que se usará para la primera y
segunda parte del pipeline. Tampoco hay documentación sobre el VLA que se pretende crear y
entrenar con los datos que generará este sistema. Todo esto se documentará a su debido tiempo
y forma, por lo que este manual está sujeto a cambios en cualquier momento.

---

## 2. Visión general del sistema

### 2.1 El problema que resuelve

Controlar un robot hoy en día es mucho más sencillo que hace 10 años, pero con el avance
actual en inteligencia artificial consideramos que puede serlo aún más. Hoy se necesita
conocimiento técnico en ROS o ROS2, saber programar, y entender las arquitecturas de
sistemas ya creados — y para cada robot todo es diferente.

Lo que se busca es facilitar ese trabajo, empezando por la familia de robots xArm; el cómo
sucede es lo que explica este manual. La idea es crear un sistema en el que un LLM pueda
ejecutar las primitivas de un robot a partir de un input en lenguaje natural. Es decir,
construir una **capa de simplificación** entre el controlador del robot y el LLM, para que
este pueda traducir el lenguaje natural a código que controle al robot de manera sencilla.

Todo esto sin ignorar los procesos de seguridad que hay que tomar en cuenta al controlar un
robot en ambientes con o sin humanos alrededor, y sin ignorar cómo la IA llegó a su
resultado: todo es auditable a través del código Python, que usa librerías que nosotros
mismos escribimos.

### 2.2 Diagrama de arquitectura

El sistema se basa actualmente en dos contenedores de Docker, para facilitar su
portabilidad.

El primer contenedor corre una imagen de la distribución ROS2 Jazzy Jalisco que contiene
todos los paquetes necesarios para conectarse al robot a través de la API de ROS2
proporcionada por UFACTORY (`xarm_ros2`), además de la librería `FredArm` en el paquete
`fred_lang_driver`.

El segundo contenedor es otro recurso proporcionado por UFACTORY: al levantarlo con el
script `run_uf_studio.sh`, se crea un firmware simulado del xArm6 (el modelo se puede
modificar dentro del script). Esto permite trabajar incluso cuando no se tiene el robot
físico, lo cual ha impulsado el desarrollo del proyecto.

Ambos contenedores se levantan con la bandera `--network host`, lo que facilita la
comunicación entre ellos. El contenedor `uf_software` expone los nodos, tópicos, servicios y
acciones de ROS2 que expondría el xArm físico; desde el contenedor `fred-lang-jazzy` creamos
clientes a esos servicios y nos suscribimos a esos tópicos.

```
┌─────────────────────────────┐        servicios ROS2        ┌──────────────────────────────┐
│  uf_software                │  ◄─────────────────────────  │  fred-lang-jazzy             │
│  (firmware simulado xArm6)  │                              │  (ROS2 Jazzy)                │
│                             │        TCP 502 / 30000-3     │                              │
│  danielwang123321/          │  ◄─────────────────────────  │  ├─ driver xarm_api (C++)    │
│  uf-ubuntu-docker           │                              │  │   expone /xarm/*          │
│                             │                              │  ├─ FredArm (cliente Python) │
│  puerto 18333 (Studio web)  │                              │  └─ xarm_ros2 (submódulo)    │
└─────────────────────────────┘                              └──────────────────────────────┘
```

### 2.3 Decisiones de diseño fundamentales

**API nativa en vez de MoveIt2.** El control se hace vía los servicios `/xarm/*` del driver,
no vía MoveIt2. MoveIt2 y Gazebo quedan diferidos como infraestructura futura. La razón no es
una limitación de hardware, sino de necesidad: actualmente las trayectorias son punto a punto
y simples, sin necesidad de planificación con evasión de obstáculos. Añadir MoveIt2 ahora
sería sumar una capa de complejidad considerable sin beneficio para lo que el proyecto hace
hoy. En algún punto se necesitará —y entonces se implementará— porque la seguridad tanto del
operador como del robot es la prioridad más alta del proyecto.

**Cliente de servicios en vez de wrapper del SDK de Python.** Se decidió que `FredArm` fuera
un cliente de los servicios `/xarm/*` y no un wrapper del SDK de Python, para tener una
portabilidad 1:1 entre el trabajo simulado y el hardware real. El mismo código sirve en ambos
casos (solo cambia la IP del robot), lo que permite hacer un sinfín de pruebas sin estar en
el laboratorio, y facilitará el entrenamiento del VLA en el futuro.

**Diseñado para el xArm6, con estructura genérica.** Toda la librería se diseña para el
xArm6, que es el modelo con el que podemos trabajar en el laboratorio, pero manteniendo una
estructura genérica para poder escalar a cualquier modelo de xArm. El fin es poder
implementar esto como una herramienta de gran escala, tanto dentro de la universidad como
fuera de ella.

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

Esta sección documenta los problemas no triviales que surgieron durante el desarrollo, su
causa raíz y cómo se resolvieron. Sirve para que un futuro desarrollador no repita el mismo
camino de depuración.

### 5.1 El `ret=3` de `motion_enable`

Al llamar a `motion_enable` en el firmware simulado, el servicio devuelve `ret=3`
(RES_TIMEOUT), mientras que `set_mode` y `set_state` y todos los demás comandos de
movimiento devuelven `ret=0` sin problema.

La causa es que el SDK de C++ v1.18.1 (el que compila el driver de `xarm_api`) espera de
forma bloqueante una trama de respuesta al opcode `MOTION_EN` con el transaction-id
correcto. El firmware v2.4.0 del simulador nunca envía esa trama; esto se verificó esperando
hasta 20 segundos. El resto de los opcodes (`SET_MODE`, `SET_STATE`, `MOVE_LINE`) sí
responden normalmente. El SDK de Python (1.18.4) no depende de ese ACK, por eso contra él el
mismo comando devuelve `ret=0`.

A pesar del `ret=3`, los servos sí se habilitan. Se comprobó con un binario de C++ mínimo
que, tras el `motion_enable`, el estado de los motores reporta todos los ejes habilitados, y
los comandos de movimiento posteriores ejecutan correctamente (los ángulos y la pose del TCP
cambian). El `ret=3` es un falso negativo del ACK, no un fallo de la operación.

**Cómo lo maneja `FredArm`.** La librería no aborta ante el `ret=3`. En vez de jalar el
cable a todo el proceso, se verifica el resultado leyendo `/xarm/robot_states`:
`servos_ok()` nos confirma que los servos están habilitados a través del bitmask `mt_able`,
y `esperar_listo()` confirma que el brazo llegó al estado READY/STANDBY sin ningún error. Es
decir, contrastamos el estado observado del robot a través de los tópicos de ROS2, no contra
el código de retorno del servicio `motion_enable`.

> **Implicaciones reales:** este comportamiento es específico del firmware v2.4.0 del
> simulador. Contra un xArm físico, `motion_enable` probablemente devuelva `ret=0`. Como
> `FredArm` verifica el estado observado en lugar de confiar solo en el `ret`, funciona en
> ambos casos sin cambios.

### 5.2 Gotchas del entorno

Tres problemas de configuración que costaron tiempo de depuración y cuya causa no era obvia
desde el síntoma.

**El paquete de Python no aparecía tras compilar.** Al crear `fred_lang_driver`,
`colcon build` terminaba "exitoso" pero `ros2 run` respondía *Package not found*, y el
paquete no figuraba en `AMENT_PREFIX_PATH` aunque sí existiera en disco. Hubo dos causas
encadenadas. Primera: hacer el primer build de un paquete nuevo con `--packages-select`
dejaba el `setup.bash` raíz del workspace desincronizado, sin registrar el paquete.
Segunda, la de fondo: el `package.xml` tenía una etiqueta XML mal cerrada
(`<exec_depend>...<exec_depend>` en vez de `</exec_depend>`), lo que hacía que `colcon`
procesara el paquete a medias — compilaba el código pero no generaba los archivos de
encadenamiento del entorno, todo sin lanzar ningún error. La lección: cuando la
infraestructura de un paquete parece rota sin motivo, recrearlo desde cero con
`ros2 pkg create` es más rápido que depurarla. Y la verdad de fondo sobre si ROS2 ve un
paquete no es buscar archivos a mano, sino `ros2 pkg executables <paquete>`.

**El driver se colgaba al conectar.** En algún momento el driver `xarm_api` se quedaba
colgado en `connect()` sin llegar a anunciar sus servicios. La causa no estaba en el
driver, sino en el contenedor del firmware: `uf_software` se había levantado en la red
`bridge` de Docker (con IP `172.17.0.2`) en vez de `--network host`. Esto pasa porque
`docker start` sobre un contenedor existente reutiliza su configuración de red original. La
solución es recrear el contenedor siempre con `docker run --network host` (lo que hace el
script `run_uf_studio.sh`), nunca revivir uno viejo con `docker start`.

**El callback de la suscripción nunca se disparaba.** Un riesgo latente al suscribirse a
tópicos de ROS2 es el desajuste de QoS: si el perfil de calidad de servicio del suscriptor
no coincide con el del publisher, los mensajes no llegan y el callback nunca se ejecuta, sin
ningún error visible. Antes de suscribirse a `/xarm/robot_states` se verificó su QoS con
`ros2 topic info /xarm/robot_states --verbose`, que reportó RELIABLE + VOLATILE — que es el
perfil por defecto de ROS2. Por eso bastó pasar una profundidad de cola simple (`10`) al
crear la suscripción. La lección general: verificar siempre el QoS del publisher antes de
suscribirse, porque otros tópicos del xArm (como `/joint_states`) usan BEST_EFFORT y ahí una
profundidad simple fallaría en silencio.

### 5.3 Lecciones de workflow

Prácticas de trabajo que se consolidaron durante el desarrollo y conviene seguir.

**El ciclo es siempre build → source → run.** Tras cada `colcon build`, hay que volver a
hacer `source` del workspace en la misma terminal antes de correr el nodo. El `source`
captura el estado del `install/` en el momento en que se ejecuta; si se compila después de
haber sourceado, la terminal sigue viendo el entorno viejo y los cambios no surten efecto (o
el paquete no aparece). Editar código sin recompilar tiene el mismo efecto: se corre la
versión anterior.

**El primer build de un paquete nuevo debe ser completo.** La primera vez que se compila un
paquete recién creado, conviene hacer `colcon build` sin `--packages-select`, para que el
`setup.bash` raíz del workspace lo registre correctamente. Una vez registrado, los builds
selectivos (`--packages-select fred_lang_driver`) ya funcionan bien para iterar rápido.

**El código se separa de los artefactos de compilación.** El código del proyecto vive en el
host y se monta dentro del contenedor; los directorios `build/`, `install/` y `log/` que
genera `colcon` no se versionan (se excluyen mediante `.gitignore`). Esto mantiene el repo
limpio y evita subir megas de archivos regenerables.

---

## 6. Guía de uso — ejemplos

<!-- PENDIENTE -->

---

## 7. Trabajo futuro

<!-- PENDIENTE -->

---

## 8. Referencias

<!-- PENDIENTE -->
