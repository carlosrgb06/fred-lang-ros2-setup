# FrED-LANG — Stack ROS2 / xArm7

Control del brazo robótico UFACTORY xArm7 mediante lenguaje natural, siguiendo una
arquitectura *Code as Policies*: un modelo de lenguaje traduce comandos en español o
inglés a código Python, que se ejecuta a través de **primitivas de movimiento
validadas por nodos de seguridad en ROS2** antes de mover el brazo.

Este repositorio contiene la **capa de infraestructura ROS2 y el gemelo digital**: el
entorno reproducible, el driver del robot y la librería de control (`FredArm`) sobre la
que se construyen las primitivas de alto nivel.

## Pipeline del sistema

```
   Persona            LLM              Python           ROS2            xArm7
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
│  (firmware simulado xArm7)  │                              │  (ROS2 Jazzy)                │
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
simulador (`robot_ip:=127.0.0.1`) y contra el xArm7 físico cambiando solo la IP.

**Decisión de arquitectura — API nativa sobre MoveIt2.** El control se hace vía los
servicios `/xarm/*` del driver, no vía MoveIt2. MoveIt2 y Gazebo quedan diferidos como
infraestructura futura (ver [Roadmap](#roadmap)) para evitar complejidad innecesaria en
esta etapa y porque el equipo de desarrollo trabaja sobre GPU integrada.

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
./xarm_scripts/xarm_start.sh 7 7; exec /bin/bash
```

El argumento `7 7` corresponde al xArm7 (la tabla de modelos de `xarm_start.sh` es
`<axis> <type>`: `5 5`=xArm5, `6 6`=xArm6, `7 7`=xArm7, `6 9`=Lite6, `6 12`=850).

> **Importante:** `uf_software` debe recrearse con `--network host` (el script ya lo
> hace). Un `docker start` sobre un contenedor previo lo revive en red `bridge`, y el
> driver no logra conectar.

### 2 · Driver `xarm_api` — contenedor `fred-lang-jazzy`

```bash
./scripts/run_container.sh
# ya dentro:
ros2 launch xarm_api xarm7_driver.launch.py robot_ip:=127.0.0.1
```

Espera el log `[TCP STATUS] CONTROL: 1, REPORT: 1` y confirma los servicios:

```bash
ros2 service list | grep /xarm
```

### 3 · Nodo `FredArm` — otra shell en `fred-lang-jazzy`

```bash
docker exec -it <id-del-contenedor> bash
source /opt/ros/jazzy/setup.bash
source /root/xarm_ws/install/setup.bash
ros2 run fred_lang_driver fred_arm
```

Salida esperada: `motion_enable(enable=1, id=8) -> ret=3` seguido de la habilitación de
los servos (ver [nota sobre `ret=3`](#nota-de-ingeniería--el-ret3-de-motion_enable)).

---

## Estado del proyecto

| Componente | Estado |
|---|---|
| Entorno Docker reproducible (ROS2 Jazzy + `xarm_ros2`) | ✅ Completo |
| Firmware simulado xArm7 end-to-end | ✅ Funcional |
| Driver `xarm_api` conectado al simulador | ✅ Funcional |
| Paquete `fred_lang_driver` (ament_python) | ✅ Creado y compilado |
| `FredArm.motion_enable()` | ✅ Validado contra el simulador |
| `FredArm` — `set_mode`, `set_state`, `set_position`, `set_servo_angle` | 🚧 En construcción |
| Suscripción a `/xarm/robot_states` (verificación de estado) | 🚧 En construcción |
| Primitivas de movimiento + integración con LLM | ⏳ Planeado |

La clase `FredArm` tiene su **molde de método validado** end-to-end (patrón cliente:
armar request → `call_async` → `spin_until_future_complete` → leer `ret`). Los métodos
restantes siguen ese mismo molde.

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
`/xarm/robot_states` reporta `mt_able = 255` (máscara de servos activos, todos los bits
en 1) y `err = 0`. Por eso `FredArm.enable()` no debe abortar ante `ret=3`, sino
confirmar el estado contra `/xarm/robot_states`.

---

## Inspección en vivo

```bash
ros2 topic list
ros2 node list
ros2 topic echo /xarm/robot_states --once     # estado del robot (state, mt_able, err, pose)
ros2 topic echo /joint_states                 # ángulos articulares (NO cartesiano)
ros2 run tf2_ros tf2_echo link_base link_eef  # pose cartesiana del efector final
ros2 interface show xarm_msgs/msg/RobotMsg     # explorar la definición del mensaje
```

---

## Simulación fake (solo cinemática)

Útil para visualizar en RViz2, pero **no expone los servicios `/xarm/*`** — no sirve para
probar la API nativa. Para eso, usar el flujo de tres contextos descrito arriba.

```bash
ros2 launch xarm_moveit_config xarm7_moveit_fake.launch.py
```

---

## Troubleshooting

| Problema | Causa | Solución |
|---|---|---|
| Paquete Python nuevo no aparece en `ros2 run` / `ros2 pkg executables` tras `colcon build` | El primer build con `--packages-select` deja el `setup.bash` raíz desincronizado; o un `package.xml` con XML malformado instala el paquete a medias | Primer build de un paquete nuevo **siempre completo** (`colcon build` sin flags) + re-`source`. Si persiste, validar `package.xml` o recrear con `ros2 pkg create`. `ros2 pkg executables <pkg>` es la verdad de fondo para saber si ROS2 lo ve |
| El driver cuelga en `connect()` y no anuncia servicios | `uf_software` quedó en red `bridge` (`docker start` reusa la config previa) | Recrear con `docker run --network host` (lo hace `run_uf_studio.sh`) |
| `docker: unknown command: docker compose` | El plugin de compose no está instalado | No es necesario — usar `docker build` / `docker run` directo |
| `E: Unable to locate package ...` durante `rosdep install` en el Dockerfile | Cada `RUN` es una capa aislada; un `apt-get update` previo no persiste | Poner `apt-get update` en el mismo `RUN` que el install que lo necesita |
| `Failed to find ... xarm_gazebo/package.sh` al compilar `xarm_moveit_config` | Se omitió `xarm_gazebo` con `--packages-skip`, pero `xarm_moveit_config` depende de él | Compilar `xarm_gazebo` siempre (no requiere GPU para compilar) |
| RViz2 no abre ventana pero `/rviz2` aparece corriendo | Falta acceso al dispositivo gráfico | Agregar `--device /dev/dri` al `docker run` |
| `git push` pide usuario/contraseña y falla | GitHub ya no soporta autenticación por password | Usar SSH (`git remote set-url origin git@github.com:...`) o un token |

---

## Roadmap

- [ ] Completar los métodos de `FredArm` (`set_mode`, `set_state`, `set_position`, `set_servo_angle`)
- [ ] Suscripción a `/xarm/robot_states` + verificación de estado (`enable()` tolerante a `ret=3`)
- [ ] Capa de primitivas de movimiento (`agarrar()`, `muevete_a()`, …)
- [ ] Capa de validación de seguridad ROS2 (bloqueo de trayectorias imposibles)
- [ ] Prueba end-to-end: comando en lenguaje natural → código Python → ejecución validada
- [ ] **Futuro:** MoveIt2 para planeación con evasión de colisiones
- [ ] **Futuro:** Gazebo con físicas reales (requiere GPU dedicada)
- [ ] **Futuro:** pipeline de generación de datos para el modelo VLA

---

## Contenedor UFACTORY Studio (opcional)

`uf_software` incluye UFACTORY Studio, una GUI web en el puerto `18333`. **Actualmente la
GUI web no conecta con el firmware simulado** (el backend no abre el socket desde un
contenedor nuevo) y se ha descartado como vía de trabajo: Studio es solo visualización y
no aporta al flujo de control elegido. El firmware y los servicios `/xarm/*` funcionan de
forma independiente a la GUI.

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
