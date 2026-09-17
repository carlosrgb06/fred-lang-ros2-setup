# FrED-LANG — Manual del Proyecto
## Capa de Control del Robot

> Documento de referencia técnica de la capa de control del brazo robótico
> UFACTORY xArm6 para el proyecto FrED-LANG.
>
> Última actualización: 2026-09-16

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

Esta sección describe cómo replicar el entorno desde cero y ponerlo a correr. El entorno es
completamente reproducible: clonar el repositorio y construir la imagen es suficiente, sin
necesidad de instalar ROS2 ni compilar nada a mano en el host.

### 3.1 Prerrequisitos

- **Docker** (`docker --version` para confirmar).
- Para gráficos (RViz2, opcional): **X11** corriendo en el host y acceso al dispositivo
  gráfico `/dev/dri`.
- **No** se requiere `docker compose` — el proyecto usa `docker build` / `docker run`
  directo.

### 3.2 Los dos contenedores y por qué están separados

El sistema usa dos contenedores (ver [sección 2.2](#22-diagrama-de-arquitectura)):

- **`fred-lang-jazzy`** — la imagen que compilamos nosotros: ROS2 Jazzy + `xarm_ros2` +
  `fred_lang_driver`.
- **`uf_software`** — el firmware simulado del xArm, provisto por UFACTORY.

Están separados a propósito. `uf_software` es una imagen de terceros ya construida
(`danielwang123321/uf-ubuntu-docker`), no parte del stack que compilamos, así que no tiene
sentido fusionarla en nuestro Dockerfile. Se maneja como un contenedor independiente que se
levanta con su propio script.

### 3.3 Instalación y build

**1. Clonar con el submódulo de `xarm_ros2`.**

```bash
git clone --recursive https://github.com/carlosrgb06/fred-lang-ros2-setup.git
cd fred-lang-ros2-setup
```

Si ya se clonó sin `--recursive`:

```bash
git submodule update --init --recursive
```

**2. Construir la imagen de ROS2.**

```bash
docker build -t fred-lang-jazzy .
```

Esto compila `xarm_ros2` completo (incluido `xarm_gazebo`) dentro de la imagen; tarda varios
minutos la primera vez. Nota: `xarm_gazebo` se compila siempre aunque la máquina no tenga
GPU, porque compilar no requiere aceleración gráfica (solo *ejecutar* Gazebo con render la
necesita). Además `xarm_moveit_config` depende de `xarm_gazebo`, así que omitir su
compilación rompe el build completo.

### 3.4 Puesta en marcha — los tres contextos

El flujo de desarrollo requiere tres contextos corriendo en paralelo.

**Contexto 1 — Firmware simulado (`uf_software`).**

```bash
./scripts/run_uf_studio.sh
# ya dentro del contenedor:
./xarm_scripts/xarm_start.sh 6 6; exec /bin/bash
```

El argumento `6 6` corresponde al xArm6 (la tabla de modelos de `xarm_start.sh` es
`<axis> <type>`: `5 5`=xArm5, `6 6`=xArm6, `7 7`=xArm7, `6 9`=Lite6, `6 12`=850).

> **Importante:** `uf_software` debe recrearse con `--network host` (el script ya lo hace).
> Revivir un contenedor previo con `docker start` lo deja en red `bridge` y el driver no
> logra conectar (ver [sección 5.2](#52-gotchas-del-entorno)).

**Contexto 2 — Driver `xarm_api` (`fred-lang-jazzy`).**

```bash
./scripts/run_container.sh
# ya dentro:
ros2 launch xarm_api xarm6_driver.launch.py robot_ip:=127.0.0.1
```

Se espera el log `[TCP STATUS] CONTROL: 1, REPORT: 1` y se confirman los servicios con
`ros2 service list | grep /xarm`. El firmware y el driver deben coincidir en modelo:
firmware `6 6` ↔ `xarm6_driver`. Se puede verificar con
`ros2 topic echo /xarm/robot_states --once`: el array `angle` debe tener 6 elementos.

**Contexto 3 — Nodo `FredArm` (otra shell en `fred-lang-jazzy`).**

Como el contenedor tiene nombre fijo, se entra directamente sin buscar su ID:

```bash
docker exec -it fred-lang-jazzy bash
source /opt/ros/jazzy/setup.bash
source /root/xarm_ws/install/setup.bash
ros2 run fred_lang_driver fred_arm
```

Recordatorio: tras cualquier cambio en el código, el ciclo es **build → source → run** en la
misma terminal (ver [sección 5.3](#53-lecciones-de-workflow)).

### 3.5 El simulador de firmware

El contenedor `uf_software` expone los mismos nodos, tópicos, servicios y acciones de ROS2
que expondría el xArm físico. Esto es lo que permite desarrollar y probar sin el robot real,
y es también la razón por la que el código transfiere 1:1 al hardware.

El contenedor incluye además una GUI web de UFACTORY Studio en el puerto `18333`, pero **esta
GUI no se usa**: no logra conectar con el firmware simulado y se ha descartado como vía de
trabajo (es solo visualización y no aporta al flujo de control elegido). El firmware y los
servicios `/xarm/*` funcionan de forma independiente a la GUI.

> **Nota sobre la simulación fake de ROS2.** Existe un launch alternativo
> (`xarm6_moveit_fake.launch.py`) que simula solo la cinemática para visualizar en RViz2.
> **No expone los servicios `/xarm/*`**, así que no sirve para probar la API nativa — para
> eso se usa el flujo de tres contextos descrito arriba.

---

## 4. La librería `FredArm`

### 4.1 Arquitectura en capas

`FredArm` está organizada como una **jerarquía de abstracción**: cada capa usa la de
abajo y esconde su complejidad. El código de más alto nivel (y en el futuro, el generado
por el LLM) trabaja con verbos semánticos, sin preocuparse por los detalles de los
servicios ROS2 subyacentes.

```
┌───────────────────────────────────────────────────────────────────────┐
│  Capa 3 — Primitivas de alto nivel   preparar()  recuperar()  home()   │
│           (verbos semánticos)        mover_a()  mover_servos_a()       │
│                                      agarrar()  soltar()  (futuro)     │
├───────────────────────────────────────────────────────────────────────┤
│  Capa 2 — Lectura y verificación de       estado_ok()  verificar_listo()│
│           estado                          hay_error()  servos_ok()     │
│                                           get_angulos()  resumen_estado()│
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
2. Llenar sus campos (casteando) request.campo = float(valor)
3. Enviar de forma asíncrona    future = cliente.call_async(request)
4. Esperar la respuesta         rclpy.spin_until_future_complete(self, future)
5. Leer el resultado            return future.result().ret
```

Un detalle del paso 2: los campos se **castean al tipo exacto que ROS2 espera** antes de
llenarlos (`float()` en poses, ángulos y velocidades; `int()` en los campos de arranque).
No es un adorno: si se pasa un `int` donde el mensaje declara un `float`, el generador de
mensajes de ROS2 no lanza una excepción de Python sino que dispara un *assert* de C que
aborta el proceso entero (`Aborted (core dumped)`). Castear en el punto donde se arma el
mensaje —la frontera con ROS2— blinda a la librería contra ese fallo sin importar qué tipo
numérico reciba (por ejemplo, un `200` entero generado por el LLM).

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

**`estado_ok(timeout=10.0)`**
Bloquea (haciendo `spin_once` en bucle) hasta que el brazo esté en READY (`state=2`), sin
error y con los servos habilitados. Es la verificación de **confirmación** que se llama
*tras* cada comando de movimiento para confirmar que terminó bien.
- `timeout` (float): tiempo máximo de espera, en segundos.
- **Retorna** (bool): `True` si el brazo llegó a estado listo; `False` si hubo error o se
  agotó el tiempo.

**`verificar_listo()`**
Verificación de **precondición**: hace un solo `spin_once` para refrescar el estado y
**lanza `FredArmError`** si el brazo no está listo en ese instante. A diferencia de
`estado_ok()` (que espera en bucle), esta mira una sola vez y falla rápido. Se usa al
inicio de cada primitiva de movimiento para no comandar un brazo que no fue arrancado.
Distingue tres casos: sin estado (`_last_state is None`, no se corrió `preparar()`), brazo
en error, y brazo no-READY.
- **Retorna:** nada si el brazo está listo.
- **Lanza** `FredArmError` si el brazo no está listo (con mensaje según el caso).

**`resumen_estado()`**
Devuelve un string legible del estado actual (`state`, `err`, `servos_ok`) para logs y
mensajes de error. Si no hay estado aún, lo indica en vez de fallar.
- **Retorna** (str): resumen del estado, o aviso de que no hay estado.

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

Por eso `estado_ok()` compara contra `state == 2` (el valor *leído*), no contra el `0`
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

### 4.5 Referencia de la API — Capa 3 (primitivas de alto nivel)

Las primitivas son los verbos semánticos que envuelven la Capa 1 con verificación
integrada. Son lo que el LLM generará mayormente, y están diseñadas para ser seguras por
construcción y legibles como una receta.

**El patrón común.** Todas las primitivas siguen la misma secuencia interna:

```
1. Validar los argumentos recibidos      (tipos, cantidad, positividad)
2. verificar_listo()                      (precondición: el brazo debe estar READY)
3. Ejecutar el servicio de Capa 1
4. Comprobar el ret del servicio
5. Confirmar el estado final con estado_ok()
```

Si cualquier paso falla, la primitiva **lanza `FredArmError`** (ver
[manejo de errores](#manejo-de-errores)). Ninguna primitiva devuelve un valor de éxito: si
no lanzó, salió bien — la ausencia de excepción es la señal de éxito. Este contrato es
deliberado y se explica abajo.

#### Arranque y recuperación

**`preparar(enable=1, id=8, mode=0, state=0)`**
Ejecuta la secuencia de arranque completa en una sola llamada
(`motion_enable → set_mode → set_state`) y confirma con `estado_ok()` que el brazo quedó en
READY. Es la primera primitiva que debe correr en cualquier sesión.
- Valida que `enable` sea `0` o `1`.
- Acepta `ret=3` en `motion_enable` como éxito (timeout cosmético del simulador; ver
  [5.1](#51-el-ret3-de-motion_enable)).
- **Retorna:** nada si el arranque tuvo éxito.
- **Lanza** `FredArmError` si algún servicio devuelve un `ret` inválido o si el brazo no
  llega a READY.

**`recuperar()`**
Saca al brazo de un estado de error: llama `clean_error()` y luego re-ejecuta el arranque
completo (vía `preparar()`). Se usa tras un `FredArmError` de movimiento para dejar el brazo
listo de nuevo.
- Detecta dos niveles de fallo: comunicación (el `ret` de `clean_error`) y efecto (el brazo
  no vuelve a READY, detectado por el `estado_ok()` dentro de `preparar()`).
- **Retorna:** nada si la recuperación tuvo éxito.
- **Lanza** `FredArmError` si `clean_error` falla o si el brazo no se recupera (error no
  limpiable por software).

#### Movimiento

**`mover_a(x, y, z, roll=π, pitch=0.0, yaw=0.0, speed=200.0, acc=2000.0)`**
Movimiento en **espacio cartesiano** — el caballo de batalla. Envuelve `set_position` con
coordenadas nombradas en vez de una lista, lo que hace más difícil que el LLM invierta el
orden o pierda un elemento.
- `x, y, z` (int | float): posición del TCP en **milímetros**.
- `roll, pitch, yaw` (int | float): orientación en **radianes**. Los defaults
  (`π, 0, 0`) dejan el efector **apuntando hacia abajo**, la orientación típica de
  pick-and-place; así `mover_a(x, y, z)` "va a ese punto mirando hacia abajo".
- `speed` (int | float, positivo): velocidad lineal del TCP, en mm/s.
- `acc` (int | float, positivo): aceleración lineal del TCP, en mm/s².
- **Retorna:** nada si el movimiento tuvo éxito.
- **Lanza** `FredArmError` si algún argumento tiene tipo inválido, si `speed`/`acc` no son
  positivos, si el brazo no está listo, si `set_position` falla (p. ej. pose inalcanzable),
  o si el brazo no vuelve a READY tras moverse.

**`mover_servos_a(angulos, num_joints=6, speed=0.35, acc=10.0)`**
Movimiento en **espacio articular**. Envuelve `set_servo_angle`.
- `angulos` (list): ángulo objetivo por junta, **en radianes**. Debe tener exactamente
  `num_joints` elementos, todos numéricos.
- `num_joints` (int): número de juntas esperado (default `6` para xArm6). Sirve para validar
  el tamaño de `angulos` contra el modelo.
- `speed` (int | float, positivo): velocidad articular, en rad/s.
- `acc` (int | float, positivo): aceleración articular, en rad/s².
- **Retorna:** nada si el movimiento tuvo éxito.
- **Lanza** `FredArmError` si `angulos` no es una lista, si su longitud no coincide con
  `num_joints`, si algún elemento no es numérico, si `speed`/`acc` no son positivos, si el
  brazo no está listo, si el servicio falla, o si no vuelve a READY.

**`home()`**
Lleva el brazo a su pose home de fábrica. Envuelve `move_gohome` con verificación.
- **Retorna:** nada si el movimiento tuvo éxito.
- **Lanza** `FredArmError` si el brazo no está listo, si `move_gohome` falla, o si no vuelve
  a READY.

#### Manejo de errores

Toda condición anómala se comunica lanzando **`FredArmError`**, una clase de excepción
propia definida en `fred_arm_error.py`. El diseño elegido es **fallar ruidoso y
detenerse**: cuando algo sale mal, la ejecución se detiene de inmediato y el error se
reporta con un mensaje descriptivo. Nada de reintentos silenciosos ni de devolver `False`
que el código generado podría ignorar por descuido.

La razón es doble. Primero, **seguridad**: detener la secuencia ante el primer fallo evita
que el robot siga ejecutando comandos sobre un estado inválido. Segundo,
**interpretabilidad**: el mensaje de cada excepción está pensado como *feedback accionable*
para que el LLM corrija su código en el siguiente intento.

La responsabilidad se reparte por capas:

- **Capa 1** devuelve el `ret` crudo del driver (`0` = éxito), fiel a la convención del SDK.
  No interpreta ni lanza.
- **Capa 3** traduce ese `ret`, el estado observado y la validación de argumentos a
  `FredArmError` cuando corresponde.
- El **orquestador** (futuro) envolverá la ejecución del código generado por el LLM en un
  `try / except FredArmError`, capturará el mensaje y se lo devolverá al LLM como feedback.
  La primitiva *lanza*; el orquestador *atrapa y traduce*. La primitiva no sabe nada del LLM.

**Frontera de validación.** La Capa 3 es la membrana entre el código no confiable que
genera el LLM y la Capa 1. Cada primitiva valida sus argumentos (tipos, cantidad,
positividad) antes de tocar el brazo. La validación es permisiva con la forma del número
(acepta `int` y `float`); el casteo al tipo exacto de ROS2 ocurre después, en la Capa 1.
La *alcanzabilidad física* de una pose no se valida en Python: el firmware es el validador
autoritativo de cinemática, y su rechazo se captura vía el `ret` del servicio (ver
[5.4](#54-recuperación-de-errores-de-movimiento)).

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
y `estado_ok()` confirma que el brazo llegó al estado READY/STANDBY sin ningún error. Es
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

### 5.4 Recuperación de errores de movimiento

Un movimiento inválido (por ejemplo, una pose fuera del alcance del brazo) no rompe el
sistema, pero deja el brazo en un estado del que hay que saber salir. Esto se caracterizó
experimentalmente contra el simulador, provocando poses imposibles a propósito.

**Cómo se manifiesta un fallo de movimiento.** Depende del estado previo del brazo:

- **Brazo limpio → pose imposible:** el servicio devuelve un `ret` negativo (p. ej. `-9`),
  el campo `err` queda en `0`, y el brazo queda en `state=1` (RUNNING "fantasma", como si
  ejecutara un movimiento que en realidad fue rechazado). Se recupera con `set_state(0)` +
  confirmación con `estado_ok()`.
- **Brazo ya en error → pose imposible:** el servicio devuelve `ret=1` y el brazo entra en
  `state=4` (STOPPED) con `err=21`.

En ambos casos el fallo se detecta por el **`ret` del servicio** (paso 4 del patrón de las
primitivas), no por `estado_ok()`. Esto justifica que las primitivas tengan dos chequeos
separados: si solo miraran `estado_ok()`, un comando rechazado que deja el brazo en `state=1`
haría que la verificación esperara en vano un movimiento que nunca va a terminar.

**Qué es `err=21`.** Es un error de la familia planificación/cinemática (ruta no
planificable, singularidad, fuera de alcance), recuperable por software. No confundir con el
código `21` de la *otra* tabla de UFACTORY: los **códigos de retorno de la API** (los `ret`)
y los **códigos de error del controlador** (el campo `err`) son dos tablas distintas que
comparten números pequeños. En la tabla de `ret`, `21` significa "modbus baudrate not
supported" — nada que ver. El `err=21` que ve `FredArm` es el de planificación.

**La secuencia de recuperación.** Lo que funciona es `clean_error()` seguido del arranque
completo (`motion_enable → set_mode → set_state → estado_ok`), que es exactamente lo que hace
la primitiva `recuperar()`. Un hallazgo importante: en este firmware **`clean_error()` por sí
solo no baja el `err=21`** — devuelve `ret=0` (comando aceptado) pero el error persiste,
incluso dejando pasar tiempo. Hace falta el re-arranque completo. Esto refuerza un principio
transversal del proyecto: **`ret=0` significa "el comando fue aceptado", no "el comando logró
su efecto"**; la confirmación real siempre viene de leer el estado con `estado_ok()`, nunca
del `ret`.

> **Nota de laboratorio.** El estado del brazo persiste entre ejecuciones del script (el
> firmware guarda su estado). Un script que deja el brazo sucio contamina la siguiente
> corrida. Para experimentos limpios, reiniciar el contenedor del simulador.

---

## 6. Guía de uso — ejemplos

Dentro de este apartado del manual se mostrarán ejemplos para familiarizar al lector con cómo se utiliza la librería. Dentro de estos ejemplos encontrará códigos completos para ejecutar ciertas misiones mientras se explica cómo y por qué funcionan estos programas; son ejecutables completos. Todo esto asumiendo que ya se tiene el entorno listo, los dos contenedores (`uf_software` y `fred-lang-jazzy`) corriendo y con `. xarm_scripts/xarm_start.sh {DOFS} {DOFS}` y `ros2 launch xarm_api xarm{numero de DOFS del robot}_driver.launch.py robot_ip:={ip del robot}` (todo esto es explicado a fondo en la sección 3.4).

### 6.1 El flujo mínimo

```python
import rclpy
from fred_lang_driver.fred_arm import FredArm
from fred_lang_driver.fred_arm_error import FredArmError

def main():
    rclpy.init()
    arm = FredArm()
    try:
        arm.preparar()                       # arranque completo -> brazo en READY
        arm.mover_a(x=206, y=0, z=150.5)     # movimiento cartesiano (efector hacia abajo)
        arm.home()                           # regreso al home de fábrica
    except FredArmError as e:
        arm.get_logger().error(f'La operación falló: {e}')
    finally:
        arm.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

El código muestra cómo se utiliza la librería `FredArm` con un flujo mínimo. Se importa `rclpy` y la librería `FredArm` y `FredArmError` para poder utilizar todo lo construido dentro de esta librería. Dentro de la función `main()` se inicia `rclpy` con su método `init()`; luego se crea `arm` como objeto de la clase `FredArm`, que a su vez hereda de la clase `Node` de ROS2, esto es crucial por cómo está construido el sistema de FrED-LANG. Este código solamente utiliza primitivas de la Capa 3 de la librería, las más esenciales para provocar un movimiento. Primero `preparar()`, que encapsula todos los servicios de la Capa 1 que hacen que el robot esté disponible para moverse; después se llama a la función `mover_a()` para mover el brazo de una posición de inicio a la seleccionada por las coordenadas que pasan como argumentos de la función; esta función encapsula con barreras de seguridad al servicio `set_position` de la Capa 1. Por último regresamos el brazo a su posición de descanso con la función `home()`, que es a su vez la cápsula del servicio de la Capa 1 `move_gohome`. Todo envuelto con un `try/except` que agarra todos los errores que puede haber lanzado el programa con la librería `FredArmError`, esto con el fin de poder recibir feedback de por qué falló el programa; de esta manera el orquestador corrige al LLM con feedback real. Por último se destruye el nodo con `destroy_node()` y se apaga `rclpy` con su función `shutdown()`.

### 6.2 Movimiento cartesiano vs. articular

```python
import rclpy
from fred_lang_driver.fred_arm import FredArm
from fred_lang_driver.fred_arm_error import FredArmError

def main():
    rclpy.init()
    arm = FredArm()
    try:
        arm.preparar()

        # --- Cartesiano: se piensa en coordenadas del efector (mm) ---
        arm.mover_a(x=206, y=0, z=150.5)

        # --- Articular: se piensa en ángulos de cada junta (radianes) ---
        arm.mover_servos_a([0.0, -0.2, 0.0, 0.2, 0.0, 0.0])

        arm.home()
    except FredArmError as e:
        arm.get_logger().error(f'La operación falló: {e}')
    finally:
        arm.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

En este ejemplo pondremos en comparación los diferentes tipos de movimientos que podemos crear utilizando la librería `FredArm` y `FredArmError`; solamente hay dos, cartesiano y angular. Para moverse con posiciones cartesianas del efector final (en mm, milímetros) debemos utilizar la misma función de Capa 3 que utilizamos en el ejemplo pasado, `mover_a()`. Este tipo de movimiento nos sirve mucho al utilizar una cámara para determinar los movimientos del brazo, como lo hará el producto final (VLA). Esta función deja el efector final por defecto mirando hacia abajo (`roll=pi, pitch=0.0, yaw=0.0`), por lo que no es necesario mandar especificaciones de esos argumentos si no requerimos mover la dirección del efector final. Luego tenemos el segundo tipo de movimiento: el movimiento angular se utiliza cuando ya tenemos una configuración de ángulos predefinida, de tal manera el robot no necesita hacer el proceso de cinemática inversa (IK) que tiene que hacer cuando se utiliza `mover_a()`. `mover_servos_a()` es la función que encapsula el servicio `set_servo_angle()` en barreras de protección y lo transforma en una función de Capa 3; la función requiere de una lista que contenga tantos ángulos en radianes (`rad`) como DOFS tiene el robot, esto se verifica por seguridad. Esta función también permite alterar el argumento `num_joints` (`default(num_joints=6)`, porque por defecto se utiliza el xArm6), que es el que determina con cuántas juntas estamos trabajando. Dentro de los dos tipos de movimientos, `mover_a()` y `mover_servos_a()`, se puede especificar la velocidad (`speed`) y la aceleración (`acc`) con la que se mueve el robot o las juntas del robot; es necesario entender que las unidades de estos parámetros varían según la función que se utilice. En `mover_a(speed=valor, acc=otro_valor)` se necesita que los valores tengan unidades de mm/s y mm/s² respectivamente, mientras que si se utiliza `mover_servos_a(speed=valor, acc=otro_valor)` los valores deben tener unidades de rad/s y rad/s². Para ambos casos los valores deben ser positivos. Los parámetros completos que aceptan estas funciones son:

- `mover_a(x, y, z, roll=pi, pitch=0.0, yaw=0.0, speed=200.0, acc=2000.0)` — aquí se ilustra la función con valores default.
- `mover_servos_a(angulos, num_joints=6, speed=0.35, acc=10.0)` — aquí se ilustra la función con valores default.

### 6.3 Manejo de errores y recuperación

```python
import rclpy
from fred_lang_driver.fred_arm import FredArm
from fred_lang_driver.fred_arm_error import FredArmError

def main():
    rclpy.init()
    arm = FredArm()
    try:
        arm.preparar()
        # Pose deliberadamente inalcanzable para forzar el fallo:
        arm.mover_a(x=300, y=0, z=99999)
    except FredArmError as e:
        arm.get_logger().error(f'Movimiento falló: {e}')
        # El brazo quedó en un estado sucio; recuperar lo deja listo de nuevo.
        try:
            arm.recuperar()
            arm.get_logger().info('Brazo recuperado, listo para reintentar.')
        except FredArmError as e2:
            arm.get_logger().error(f'Recuperación falló (error no recuperable): {e2}')
    finally:
        arm.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

Cuando utilizamos las funciones que permiten mover el brazo podemos llegar a cometer errores como poses inalcanzables, argumentos mal escritos, etc. Todo esto se trata de atrapar con la clase `FredArmError`; si esta no lo hace, lo hará el mismo firmware del robot. Es importante saber qué es lo que se requiere hacer cuando el brazo queda en un estado de error. Este ejemplo muestra cómo se causa y se recupera de un error. Primero se usa la función `mover_a()` con un argumento de `z` que hace que la posición deseada sea inalcanzable; la primitiva detecta el fallo por el `ret` del servicio (lanzando `FredArmError`) y, como consecuencia, el robot queda en un estado que no es 2 (READY/SLEEPING), por lo que la siguiente función no podrá realizar su objetivo. Para cuando esto suceda se implementó la función de Capa 3 `recuperar()`, que en esencia es simplemente el encapsulamiento de la función de Capa 1 `clean_error()` (que no garantiza limpiar el estado de error del robot) y de la función de Capa 3 `preparar()`. `recuperar()` podría considerarse como un tipo de reinicio para poder regresar a un estado listo para movimiento, y registra el error con `FredArmError` de tal manera que el orquestador podrá corregir al LLM. Si la función `recuperar()` no logró regresar al robot a un estado que permita movimiento, se recomienda reiniciar todo el ambiente simulado. Si no se está utilizando el ambiente simulado, seguir todos los protocolos de seguridad del laboratorio.

### 6.4 Uso avanzado: bajar a la Capa 1

```python
import rclpy
from fred_lang_driver.fred_arm import FredArm

def main():
    rclpy.init()
    arm = FredArm()

    # Arranque manual (sin la primitiva preparar):
    arm.motion_enable(1, 8)
    arm.set_mode(0)
    arm.set_state(0)

    # Verificación a mano: aquí NO hay red de seguridad automática.
    if not arm.estado_ok():
        arm.get_logger().error('El brazo no llegó a READY.')
        arm.destroy_node()
        rclpy.shutdown()
        return

    # Servicio directo: devuelve el ret crudo del driver (0 = éxito).
    ret = arm.set_position([206.0, 0.0, 150.5, 3.1416, 0.0, 0.0])
    arm.get_logger().info(f'set_position -> ret={ret}')
    arm.estado_ok()   # confirmar a mano que terminó bien

    arm.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
```

Mientras que se diseñó la librería con funciones de Capa 3 que encapsulan a las de Capa 1, la Capa 1 sigue expuesta para el LLM y el usuario. Se diseñó la librería para que todo estuviera a la mano y a la vez se facilitara la tarea para el LLM. Usar estas funciones te garantiza un control más fino sobre el robot, pero tienes que haber aprendido bien sobre los argumentos y funcionalidades completas de estos servicios. Cuando se utiliza la Capa 1 no hay verificaciones de seguridad; todo se tiene que verificar apoyándose en funciones de Capa 2, el usuario es responsable al 100% de lo que ocurre y cómo ocurre. Estas funciones de Capa 1 sí tienen un return: es el código que arroja el servicio propio de ROS2. Estos `ret` se pueden interpretar, pero en general el estándar es que salgan con éxito (`ret=0`). Para poner un ejemplo concreto sobre cómo la Capa 3 simplifica a la Capa 1: si se utiliza la Capa 1 para preparar al robot para hacer un movimiento se requieren tres funciones, `motion_enable(enable, id)`, `set_mode(mode)` y `set_state(state)`, y es necesario entender qué hacen todos y cada uno de los parámetros que utilizan estas funciones; mientras que si se utiliza la función `preparar()` de Capa 3, todo este proceso se hace en automático con verificaciones de seguridad que te advierten si el robot no llegó al estado deseado. Si quieres verificar si se llegó al estado deseado sin utilizar la Capa 3, se necesita apoyar de la Capa 2 y utilizar la función `estado_ok()`.

### 6.5 Una tarea completa: pick-and-place

```python
import rclpy
from fred_lang_driver.fred_arm import FredArm
from fred_lang_driver.fred_arm_error import FredArmError

def main():
    rclpy.init()
    arm = FredArm()
    try:
        arm.preparar()

        # 1. Ir sobre el objeto y bajar
        arm.mover_a(x=206, y=0, z=200)       # posición de aproximación
        arm.mover_a(x=206, y=0, z=150.5)     # bajar al objeto

        # 2. Agarrar (pendiente de hardware — la pinza no está en el sim)
        # arm.agarrar()

        # 3. Subir y llevar al destino
        arm.mover_a(x=206, y=0, z=200)       # subir con el objeto
        arm.mover_a(x=100, y=150, z=200)     # mover al destino
        arm.mover_a(x=100, y=150, z=150.5)   # bajar en el destino

        # 4. Soltar (pendiente de hardware)
        # arm.soltar()

        # 5. Volver a home
        arm.mover_a(x=100, y=150, z=200)     # subir
        arm.home()
    except FredArmError as e:
        arm.get_logger().error(f'La tarea falló: {e}')
    finally:
        arm.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
```

Este último ejemplo ilustra una misión completa de pick-and-place utilizando funciones de Capa 3 (como normalmente lo hará el LLM); una secuencia de verbos semánticos se programa como una receta. Aquí se utiliza todo el flujo: primero se prepara el brazo con `preparar()`, luego se mueve el brazo a una posición deseada previamente calculada con `mover_a()`, posteriormente se activa el gripper con `agarrar()` (función que estará próximamente en la librería). Ya que se tiene el objeto agarrado, te mueves con la misma función `mover_a()` y sueltas el objeto donde deseas con `soltar()` (función que estará próximamente en la librería); luego regresa el brazo a una posición de reposo, como lo puede ser la posición de home, utilizando la función `home()`. Cualquier fallo se atrapa por `FredArmError` y se utiliza como feedback para el usuario, ya sea el LLM o un humano. Para completar todo este proceso es necesario importar las librerías necesarias (`rclpy`, `FredArm`, `FredArmError`) y no olvidar programar lo básico que se mostró en el ejemplo 1 (sección 6.1).

---

## 7. Trabajo futuro

<!-- PENDIENTE -->

---

## 8. Referencias

<!-- PENDIENTE -->
