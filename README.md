# FrED-LANG — Stack ROS2 / xArm6

Control del brazo robótico UFACTORY xArm6 mediante lenguaje natural, siguiendo una
arquitectura *Code as Policies*: un modelo de lenguaje traduce comandos en español o
inglés a código Python, que se ejecuta a través de **primitivas de movimiento
validadas por nodos de seguridad en ROS2** antes de mover el brazo.

Este repositorio contiene la **capa de infraestructura ROS2 y el gemelo digital**: el
entorno reproducible, el driver del robot y la librería de control (`FredArm`) sobre la
que se construyen las primitivas de alto nivel.

## Pipeline del sistema

```
   Persona            LLM              Python           ROS2            xArm6
  "agarra la    →   traduce a     →   primitivas   →  validación  →   ejecución
  pieza roja"      código Python     de movimiento    de seguridad    en el robot
```

**Principios de diseño:**

- **Seguridad** — ROS2 bloquea trayectorias imposibles antes de mover el brazo. Cero
  choques.
- **Interpretabilidad** — no es una "caja negra": si algo falla, el script de Python
  generado es legible y auditable.

La visión a largo plazo es usar este pipeline como generador de datos para entrenar un
modelo Vision-Language-Action (VLA) end-to-end.

---

## Arquitectura

El sistema corre en **dos contenedores Docker**, ambos con `--network host`:

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

**Capa de control — `FredArm`.** `FredArm` es un **cliente delgado** de los servicios
nativos `/xarm/*`. No se comunica con el hardware directamente ni envuelve el SDK de
Python: habla únicamente con el driver oficial C++ (`xarm_api`) a través de servicios
ROS2. La ventaja clave es la **portabilidad 1:1**: el mismo código funciona contra el
simulador (`robot_ip:=127.0.0.1`) y contra el xArm6 físico cambiando solo la IP.

La librería se organiza en **dos niveles**:

- **Capa 1 — bajo nivel:** clientes directos de los servicios `/xarm/*` y lectura de
  estado. Devuelven el `ret` crudo del driver; no verifican, no lanzan. Son la base sobre
  la que se construye todo lo demás y quedan disponibles para uso avanzado.
- **Capa 3 — alto nivel:** primitivas que envuelven la Capa 1 con verificación integrada y
  comunican los fallos lanzando `FredArmError` (ver [Primitivas de alto nivel](#primitivas-de-alto-nivel--capa-3)).

**Métodos de `FredArm` (Capa 1 — bajo nivel):**

| Grupo | Método | Servicio / fuente | Función |
|---|---|---|---|
| Arranque | `motion_enable(enable, id=8)` | `/xarm/motion_enable` | Habilita/deshabilita los servos |
| Arranque | `set_mode(mode)` | `/xarm/set_mode` | Fija el modo (0 = posición) |
| Arranque | `set_state(state)` | `/xarm/set_state` | Fija el estado (0 = READY) |
| Movimiento | `set_position(pose, ...)` | `/xarm/set_position` | Movimiento cartesiano (el firmware resuelve IK) |
| Movimiento | `set_servo_angle(angles, ...)` | `/xarm/set_servo_angle` | Movimiento articular (ángulos directos) |
| Movimiento | `move_gohome(...)` | `/xarm/move_gohome` | Home de fábrica (articular) |
| Estado | `hay_error()` | tópico `robot_states` | ¿Hay código de error? |
| Estado | `servos_ok()` | tópico `robot_states` | ¿Servos habilitados? (bitmask `mt_able`) |
| Estado | `estado_ok(timeout)` | tópico `robot_states` | Bloquea hasta READY, sin error, servos ok (confirmación) |
| Estado | `verificar_listo()` | tópico `robot_states` | Precondición: lanza si el brazo no está listo *ahora* |
| Estado | `get_angulos()` | tópico `robot_states` | Ángulos articulares actuales |
| Recuperación | `clean_error()` | `/xarm/clean_error` | Limpia el código de error |

**Todos los `request` de Capa 1 castean sus campos al tipo que ROS2 exige** (`float()` en
poses/ángulos/velocidades, `int()` en los de arranque) antes de enviarlos. Un `int` donde
el mensaje espera un `float` no dispara una excepción de Python sino un *assert* de C que
aborta el proceso (`core dumped`); el casteo defensivo en el punto donde se arma el
mensaje evita ese modo de fallo sin importar quién llame al método.

**Decisión de arquitectura — API nativa sobre MoveIt2.** El control se hace vía los
servicios `/xarm/*` del driver, no vía MoveIt2. MoveIt2 y Gazebo quedan diferidos como
infraestructura futura (ver [Roadmap](#roadmap)) para evitar complejidad innecesaria en
esta etapa y porque el equipo de desarrollo trabaja sobre GPU integrada.

**Espacio articular vs. cartesiano.** La librería expone las dos formas de mover el brazo:
`set_servo_angle` (le das los 6 ángulos de junta, en radianes) y `set_position` (le das la
pose del efector final y el firmware resuelve la cinemática inversa). El flujo principal es
**cartesiano** (`set_position`), porque se alinea con cómo una cámara percibe el mundo —
coordenadas, no ángulos — de cara al futuro modelo VLA. El articular se reserva para poses
fijas conocidas como el *home*, donde guardar los ángulos evita recalcular IK.

**Lectura de estado.** `FredArm` se suscribe al tópico `/xarm/robot_states` y guarda el
último mensaje (`_last_state`). Sobre él construye **dos verificaciones con propósitos
distintos**, que comparten forma pero no intención:

- `estado_ok(timeout)` — **confirmación** (la película). Bloquea haciendo `spin_once` en un
  bucle hasta que el brazo esté en READY, sin error y con los servos habilitados, o hasta
  agotar el `timeout`. Devuelve `True`/`False`. Se usa *después* de un movimiento para
  confirmar que terminó bien. Convierte cada comando de "manda y reza" a "manda y confirma":
  `wait=True` solo garantiza que el movimiento *terminó*; `estado_ok()` garantiza que
  *terminó bien*.
- `verificar_listo()` — **precondición** (la foto). Hace un solo `spin_once` para refrescar
  el estado y lanza `FredArmError` si el brazo no está listo *en este instante* (sin
  comunicación, en error, o no-READY). Se usa *antes* de mover, para no mandar un comando a
  un brazo que no fue arrancado con `preparar()`.

`_last_state` arranca en `None` y solo se llena cuando algo hace `spin`; por eso ambas
verificaciones spinean antes de leerlo, y `verificar_listo()` distingue explícitamente el
caso `None` (sin comunicación / falta `preparar()`) del caso "hay estado pero no es READY".

### Primitivas de alto nivel — Capa 3

Las primitivas son verbos de alto nivel que envuelven la Capa 1 con verificación
integrada. Están pensadas para ser lo que el LLM genera: se leen como recetas y son seguras
por construcción. Todas siguen el **mismo patrón**:

```
validar argumentos → verificar_listo() → ejecutar servicio Capa 1
                   → comprobar ret → confirmar con estado_ok()
```

Ninguna devuelve un valor de éxito: **si la primitiva no lanzó, salió bien** (la ausencia
de excepción es la señal de éxito).

| Primitiva | Envuelve | Función |
|---|---|---|
| `preparar(...)` | arranque completo | `motion_enable → set_mode → set_state` y confirma READY |
| `recuperar()` | `clean_error` + `preparar` | Saca al brazo de un error y lo re-arranca |
| `mover_a(x, y, z, roll, pitch, yaw, ...)` | `set_position` | Movimiento cartesiano; coordenadas nombradas, orientación por defecto "efector hacia abajo" |
| `mover_servos_a(angulos, num_joints=6, ...)` | `set_servo_angle` | Movimiento articular; valida cantidad y tipo de ángulos |
| `home()` | `move_gohome` | Regresa al home de fábrica |

**Frontera de validación.** La Capa 3 es la membrana entre el código no confiable que
genera el LLM y la Capa 1. Cada primitiva **valida sus argumentos** (tipos, cantidad,
positividad) y lanza `FredArmError` con un mensaje accionable antes de tocar el brazo. La
validación es permisiva con la forma del número (acepta `int` y `float`); el casteo al tipo
exacto de ROS2 ocurre después, en la Capa 1. La *alcanzabilidad física* de una pose no se
valida en Python: el firmware es el validador autoritativo de cinemática, y su fallo se
captura vía el `ret` del servicio.

### Manejo de errores — `FredArmError`

Toda condición anómala se comunica lanzando `FredArmError` (clase propia en
`fred_arm_error.py`). El sistema **falla ruidoso y se detiene**: nada de reintentos
silenciosos ni de devolver `False` que el código generado podría ignorar. El mensaje de
cada excepción es descriptivo y accionable, pensado como *feedback* para que el LLM corrija
su código.

Separar responsabilidades por capa:

- **Capa 1** devuelve el `ret` crudo del driver (`0` = éxito), fiel a la convención del
  SDK. No interpreta ni lanza.
- **Capa 3** traduce: `ret != 0`, estado no-READY tras el movimiento, o argumentos
  inválidos → `FredArmError`.
- El **orquestador** (futuro) envolverá la ejecución del código del LLM en un `try/except
  FredArmError`, capturará el mensaje y lo devolverá al LLM como feedback. La primitiva
  *lanza*; el orquestador *atrapa y traduce*. La primitiva no sabe nada del LLM.

Una excepción hereda dos niveles de detección: por ejemplo `recuperar()` distingue un fallo
de comunicación (`clean_error` con `ret != 0`) de un fallo de efecto (el brazo no vuelve a
READY, detectado por el `estado_ok()` dentro de `preparar()`), cada uno con su propio
mensaje.

---

## Prerrequisitos

- Docker (`docker --version` para confirmar)
- Para gráficos (RViz2 opcional): X11 en el host y acceso a `/dev/dri`
- No se requiere `docker compose` — este repo usa `docker build` / `docker run` directo

---

## Instalación

### 1. Clonar con el submódulo de `xarm_ros2`

```bash
git clone --recursive https://github.com/carlosrgb06/fred-lang-ros2-setup.git
cd fred-lang-ros2-setup
```

Si ya lo clonaste sin `--recursive`:

```bash
git submodule update --init --recursive
```

### 2. Construir la imagen de ROS2

```bash
docker build -t fred-lang-jazzy .
```

Compila `xarm_ros2` completo (incluido `xarm_gazebo`) dentro de la imagen. Tarda varios
minutos la primera vez. `xarm_gazebo` se compila siempre aunque la máquina no tenga GPU:
compilar no requiere aceleración gráfica, solo *ejecutar* Gazebo con render la necesita.
Además `xarm_moveit_config` depende de `xarm_gazebo`, así que omitir su compilación rompe
el build.

---

## Puesta en marcha

El flujo de desarrollo requiere **tres contextos** corriendo en paralelo.

### 1 · Firmware simulado — contenedor `uf_software`

```bash
./scripts/run_uf_studio.sh
# ya dentro del contenedor:
./xarm_scripts/xarm_start.sh 6 6; exec /bin/bash
```

El argumento `6 6` corresponde al xArm6 (la tabla de modelos de `xarm_start.sh` es
`<axis> <type>`: `5 5`=xArm5, `6 6`=xArm6, `7 7`=xArm7, `6 9`=Lite6, `6 12`=850).

> **Importante:** `uf_software` debe recrearse con `--network host` (el script ya lo
> hace). Un `docker start` sobre un contenedor previo lo revive en red `bridge`, y el
> driver no logra conectar.

### 2 · Driver `xarm_api` — contenedor `fred-lang-jazzy`

```bash
./scripts/run_container.sh
# ya dentro:
ros2 launch xarm_api xarm6_driver.launch.py robot_ip:=127.0.0.1
```

Espera el log `[TCP STATUS] CONTROL: 1, REPORT: 1` y confirma los servicios:

```bash
ros2 service list | grep /xarm
```

> El firmware y el driver deben coincidir en modelo: firmware `6 6` ↔ `xarm6_driver`. Se
> puede verificar con `ros2 topic echo /xarm/robot_states --once`: el array `angle` debe
> tener **6** elementos.

### 3 · Nodo `FredArm` — otra shell en `fred-lang-jazzy`

```bash
docker exec -it <id-del-contenedor> bash
source /opt/ros/jazzy/setup.bash
source /root/xarm_ws/install/setup.bash
ros2 run fred_lang_driver fred_arm
```

El `main()` de ejemplo ejecuta la secuencia de arranque y movimientos de prueba con
verificación de estado. El flujo recomendado usa las primitivas de Capa 3 dentro de un
`try/except FredArmError`:

```python
arm = FredArm()
try:
    arm.preparar()
    arm.mover_a(x=206, y=0, z=150.5)   # cartesiano, efector hacia abajo
    arm.home()
except FredArmError as e:
    arm.get_logger().error(f'Fallo: {e}')
    # aquí el orquestador llamaría arm.recuperar() y reintentaría
```

---

## Estado del proyecto

| Componente | Estado |
|---|---|
| Entorno Docker reproducible (ROS2 Jazzy + `xarm_ros2`) | ✅ Completo |
| Firmware simulado xArm6 end-to-end | ✅ Funcional |
| Driver `xarm_api` conectado al simulador | ✅ Funcional |
| Paquete `fred_lang_driver` (ament_python) | ✅ Creado y compilado |
| **Capa 1 — control de bajo nivel** | ✅ **Completa y probada** |
| ↳ Arranque (`motion_enable`, `set_mode`, `set_state`) | ✅ Validado |
| ↳ Movimiento (`set_position`, `set_servo_angle`, `move_gohome`) | ✅ Validado — el brazo se mueve |
| ↳ Lectura de estado (suscripción + `estado_ok`, `verificar_listo`, `hay_error`, `servos_ok`, `get_angulos`) | ✅ Validado |
| ↳ Recuperación (`clean_error`) | ✅ Validado |
| ↳ Casteo defensivo de tipos en todos los `request` | ✅ Implementado |
| **Capa 3 — primitivas de alto nivel** | ✅ **Completa** |
| ↳ `preparar`, `recuperar` (arranque + recuperación) | ✅ Validado |
| ↳ `mover_a` (cartesiano), `mover_servos_a` (articular), `home` | ✅ Implementado |
| ↳ Manejo de errores por `FredArmError` + `verificar_listo` | ✅ Implementado |
| Pinza / gripper | ⏳ Pendiente de hardware (el sim no expone actuador) |
| Nodo orquestador + integración con LLM | ⏳ Planeado |

Los métodos de Capa 1 están verificados objetivamente contra el simulador: los movimientos
cambian la pose/ángulos según lo comandado (`ret=0`, `err=0`), y `estado_ok()` confirma el
estado READY tras cada uno leyendo `/xarm/robot_states`. La recuperación de errores de
planificación (`err=21`) está confirmada experimentalmente (ver
[Nota de ingeniería](#nota-de-ingeniería--recuperación-de-errores)).

---

## Nota de ingeniería — el `ret=3` de `motion_enable`

El servicio `motion_enable` devuelve `ret=3` (RES_TIMEOUT) contra el firmware simulado.
**Es un comportamiento cosmético, no un error funcional**, y su causa raíz está
diagnosticada:

- El SDK **C++ v1.18.1** (el que compila `xarm_api`) espera de forma bloqueante una trama
  de respuesta al opcode `MOTION_EN` con el transaction-id correcto.
- El firmware **v2.4.0** del simulador nunca envía esa trama (verificado esperando hasta
  20 s). El resto de opcodes (`SET_MODE`, `SET_STATE`, `MOVE_LINE`) responden normal.
- El SDK **Python 1.18.4** no depende de ese ACK, por eso ahí devuelve `ret=0`.

**Verificación de que los servos sí se habilitan:** tras `motion_enable`, el tópico
`/xarm/robot_states` reporta `mt_able = 63` (`0b111111` — los 6 servos del xArm6 activos) y
`err = 0`. Por eso `FredArm` no aborta ante `ret=3`; confirma el estado con `estado_ok()` /
`servos_ok()` en su lugar. `servos_ok()` compara `mt_able & ((1<<6)-1) == 63`.

---

## Nota de ingeniería — recuperación de errores

Una pose inalcanzable se manifiesta de dos formas distintas según el estado previo del
brazo, ambas confirmadas experimentalmente contra el simulador:

- **Brazo limpio → pose imposible:** el servicio devuelve un `ret` negativo (p. ej. `-9`),
  `err` queda en `0` y el brazo queda en `state=1` (RUNNING "fantasma"). Se recupera con
  `set_state(0)` + `estado_ok()`.
- **Brazo ya en error → pose imposible:** el servicio devuelve `ret=1` y el brazo entra en
  `state=4` (STOPPED) con `err=21` (familia planificación/cinemática, recuperable por
  software).

**La secuencia de recuperación que funciona es `clean_error()` seguido del arranque
completo** (`motion_enable → set_mode → set_state → estado_ok`), que es exactamente lo que
hace la primitiva `recuperar()`. Hallazgo importante: `clean_error()` **por sí solo no
baja el `err=21`** en este firmware (devuelve `ret=0` sin limpiar, ni con espera de por
medio); hace falta el re-arranque completo. La confirmación real del éxito viene siempre de
`estado_ok()` leyendo el estado, no del `ret` de `clean_error()`.

> **Trampa de las dos tablas.** UFACTORY tiene *dos* tablas de códigos con números
> pequeños que se confunden con facilidad: los **códigos de retorno de la API** (los `ret`
> de las funciones — ahí `21` es "modbus baudrate not supported") y los **códigos de error
> del controlador** (el campo `err` de `/xarm/robot_states` — ahí `21` es de planificación
> /cinemática). El `err=21` que ve `FredArm` es el segundo. No confundir `ret` con `err`.

---

## Inspección en vivo

```bash
ros2 topic list
ros2 node list
ros2 topic echo /xarm/robot_states --once     # estado del robot (state, mode, mt_able, err, angle, pose)
ros2 topic echo /joint_states                 # ángulos articulares (NO cartesiano)
ros2 run tf2_ros tf2_echo link_base link_eef  # pose cartesiana del efector final
ros2 interface show xarm_msgs/srv/MoveCartesian  # definición del servicio de movimiento cartesiano
ros2 interface show xarm_msgs/srv/MoveJoint      # definición del servicio de movimiento articular
ros2 interface show xarm_msgs/msg/RobotMsg       # definición del mensaje de estado
```

**Tabla de referencia — campos de `robot_states`:**

- `state` (leído): 1 = RUNNING, 2 = SLEEPING (READY), 3 = PAUSED, 4 = STOPPED,
  5 = CONFIG_CHANGED. (Los estados que se *fijan* con `set_state` usan otra tabla;
  `set_state(0)` se reporta como `state: 2`.)
- `mode`: 0 = posición, 1 = servoj, 2 = teaching. (En modo 0 el `set_mode` acepta hasta 7
  según firmware.)
- `mt_able`: máscara de bits de servos habilitados.
- `err` / `warn`: 0 = sin error. `set_state(0)` limpia el error.
- `angle`: ángulos de junta (6 para xArm6). `pose`: `[x, y, z, roll, pitch, yaw]`
  (XYZ en mm, orientación en rad).

---

## Simulación fake (solo cinemática)

Útil para visualizar en RViz2, pero **no expone los servicios `/xarm/*`** — no sirve para
probar la API nativa. Para eso, usar el flujo de tres contextos descrito arriba.

```bash
ros2 launch xarm_moveit_config xarm6_moveit_fake.launch.py
```

---

## Troubleshooting

| Problema | Causa | Solución |
|---|---|---|
| Paquete Python nuevo no aparece en `ros2 run` / `ros2 pkg executables` tras `colcon build` | El primer build con `--packages-select` deja el `setup.bash` raíz desincronizado; o un `package.xml` con XML malformado instala el paquete a medias | Primer build de un paquete nuevo **siempre completo** (`colcon build` sin flags) + re-`source`. Si persiste, validar `package.xml` o recrear con `ros2 pkg create`. `ros2 pkg executables <pkg>` es la verdad de fondo para saber si ROS2 lo ve |
| Cambios en el código no surten efecto al correr el nodo | Falta `colcon build` tras editar, o falta re-`source` tras el build | El ciclo es siempre **build → source → run**, en la misma terminal |
| El callback de una suscripción nunca se dispara | QoS del suscriptor no coincide con el del publisher | Verificar con `ros2 topic info <topic> --verbose`; igualar Reliability/Durability. (`robot_states` es RELIABLE+VOLATILE = default, basta profundidad 10) |
| El driver cuelga en `connect()` y no anuncia servicios | `uf_software` quedó en red `bridge` (`docker start` reusa la config previa) | Recrear con `docker run --network host` (lo hace `run_uf_studio.sh`) |
| Movimiento cartesiano falla con error C40 | Con `motion_type=0` (lineal), la pose objetivo no es alcanzable en línea recta o no tiene IK válida | Usar poses alcanzables cercanas, o considerar `motion_type` 1/2 (requiere firmware >= 1.11.100) |
| El brazo queda en `err=21` / `state=4` tras una pose imposible y no vuelve a moverse | Error de planificación/cinemática; `clean_error()` solo no lo limpia en este firmware | Llamar `recuperar()` (= `clean_error` + arranque completo) y confirmar con `estado_ok()`. Un script nuevo hereda el estado sucio: reiniciar el contenedor del sim para partir limpio |
| El programa muere con `Aborted (core dumped)` en un movimiento | Se pasó un `int` (u otro tipo) donde el mensaje ROS2 espera `float`; el generador de mensajes hace un *assert* de C | Usar las primitivas de Capa 3 (validan y castean) o pasar `float` explícito a los métodos de Capa 1. La Capa 1 ya castea sus `request`, pero una versión previa podría no hacerlo |
| `docker: unknown command: docker compose` | El plugin de compose no está instalado | No es necesario — usar `docker build` / `docker run` directo |
| `E: Unable to locate package ...` durante `rosdep install` en el Dockerfile | Cada `RUN` es una capa aislada; un `apt-get update` previo no persiste | Poner `apt-get update` en el mismo `RUN` que el install que lo necesita |
| `Failed to find ... xarm_gazebo/package.sh` al compilar `xarm_moveit_config` | Se omitió `xarm_gazebo` con `--packages-skip`, pero `xarm_moveit_config` depende de él | Compilar `xarm_gazebo` siempre (no requiere GPU para compilar) |
| RViz2 no abre ventana pero `/rviz2` aparece corriendo | Falta acceso al dispositivo gráfico | Agregar `--device /dev/dri` al `docker run` |
| `git push` pide usuario/contraseña y falla | GitHub ya no soporta autenticación por password | Usar SSH (`git remote set-url origin git@github.com:...`) o un token |

---

## Roadmap

- [x] Métodos base de `FredArm` (Capa 1): arranque, movimiento, lectura de estado, recuperación
- [x] Casteo defensivo de tipos en todos los `request` de Capa 1
- [x] Capa 3 — primitivas de alto nivel (`preparar`, `recuperar`, `mover_a`, `mover_servos_a`, `home`) con verificación integrada y manejo de errores por `FredArmError`
- [ ] Pinza / gripper (pendiente de levantar el firmware con actuador; los servicios de gripper Lite6 usan el tipo `Call`)
- [ ] Nodo orquestador + integración LLM (Code as Policies vía `exec()`)
- [ ] Prueba end-to-end: comando en lenguaje natural → código Python → ejecución validada
- [ ] Migración a hardware real (cambiar `robot_ip`)
- [ ] **Futuro:** MoveIt2 para planeación con evasión de colisiones
- [ ] **Futuro:** Gazebo con físicas reales (requiere GPU dedicada)
- [ ] **Futuro:** pipeline de generación de datos para el modelo VLA

---

## Contenedor UFACTORY Studio (opcional)

`uf_software` incluye UFACTORY Studio, una GUI web en el puerto `18333`. **La GUI web no
conecta con el firmware simulado** (el backend no abre el socket desde un contenedor nuevo)
y se ha descartado como vía de trabajo: Studio es solo visualización y no aporta al flujo
de control elegido. El firmware y los servicios `/xarm/*` funcionan de forma independiente
a la GUI.

Si en el futuro se quiere la UI, la opción es correr Studio de escritorio en el host
apuntando a `127.0.0.1` con `uf_software` levantado — con expectativa baja y sin bloquear
el proyecto por ello.

---

## Referencia — lectura del SDK del xArm

Orden recomendado dentro del SDK oficial:

1. `README`
2. Máquina de modos/estados en `xarm_api.md`
3. Códigos de error en `xarm_api_code.md`
4. Ejemplos numerados en `example/wrapper/common/`

(Los `< >` en la documentación de comandos son notación, no caracteres literales.)
