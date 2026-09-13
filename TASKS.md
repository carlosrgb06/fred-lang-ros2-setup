# FrED-LANG — Goals & Tasks

> Última actualización: 2026-09-13
> Deadline del entregable: ~3 semanas desde finales de agosto 2026

Convención de estado: `[ ]` pendiente · `[x]` hecho · `[~]` en progreso · `[!]` bloqueado

> **Nota de modelo:** el proyecto ahora usa **xArm6** (6 DOF), no xArm7. Firmware con
> `xarm_start.sh 6 6` y driver `xarm6_driver.launch.py`. Los métodos de arranque
> (`motion_enable`/`set_mode`/`set_state`) son agnósticos al número de ejes; los de
> movimiento usan arrays de 6 (angles) / 6 (pose).

---

## Goal 1 — Entorno de desarrollo reproducible ✅

- [x] Repo `carlosrgb06/fred-lang-ros2-setup` publicado
- [x] Contenedor ROS2 Jazzy (vía rocker) con `xarm_ros2` (branch `jazzy`) como submódulo
- [x] Fix de Dockerfile: `apt-get update` en el mismo layer que los installs
- [x] `/dev/dri` pasado al contenedor para render de RViz2
- [ ] Habilitar a un colaborador a replicar el entorno completo
  - [!] Bloqueado: issue de `docker buildx` en su máquina — pendiente de resolver
- [x] Agregar el contenedor de UFACTORY Studio (`uf-ubuntu-docker`) al repo `fred-lang-ros2-setup`
  - Contenedor separado (no se fusiona con el de ROS2 Jazzy)
  - Documentado en el README el comando de arranque correcto
  - Script `run_uf_studio.sh` que automatiza el arranque

---

## Goal 2 — Simulador nativo del xArm6 funcionando end-to-end ✅

- [x] Decidido: usar API nativa de xArm (`xarm_api`) en vez de MoveIt2 por ahora
- [x] Contenedor `uf_software` (UFACTORY Studio simulator) corriendo en `--network host`
- [x] Firmware simulado arrancado correctamente como xArm6 (`xarm_start.sh 6 6`)
- [x] Driver `xarm_api` lanzado (`xarm6_driver.launch.py robot_ip:=127.0.0.1`)
- [x] Servicios nativos `/xarm/...` confirmados con `ros2 service list`
- [x] Verificado: `motion_enable` + `set_mode` + `set_state` + `set_position` → el brazo se mueve
- [x] **RESUELTO — el `ret=3` de `motion_enable` es cosmético.** Análisis abajo.
- [!] UFACTORY Studio (`localhost:18333`): abandonado como vía. La GUI web no conecta al
      firmware sim (backend no abre el socket; sin perilla de IP). No bloqueante — Studio
      es solo visualización; se sigue sin él.

### Diagnóstico del `ret=3` de `motion_enable` (2026-09-03)

**Causa raíz:** el SDK **C++ v1.18.1** (el que compila `xarm_api`) espera de forma bloqueante una
trama de respuesta al opcode `MOTION_EN` (11) con el transaction-id correcto. El firmware **v2.4.0**
del simulador **nunca envía esa trama** (probado esperando hasta 20 s con `set_timeout(20)`: sigue
`ret=3`). El resto de opcodes (`SET_MODE`, `SET_STATE`, `MOVE_LINE`) responden normal. El SDK
**Python 1.18.4** no depende de ese ACK → por eso ahí da `ret=0`.

**Es cosmético, no funcional.** Probado con un binario C++ mínimo sin ROS2 ni el hilo de
`/joint_states` (`xarm_sdk/cxx/example/9999-fredlang_enable_probe.cc`):
- `motion_enable` → `ret=3`, pero `motor_enable_states = [1,1,...]` → los servos SÍ se habilitan
- `set_mode(0)` / `set_state(0)` → `ret=0`
- `set_position` → `ret=0`; ángulos de joints y TCP cambian → el brazo se mueve de verdad

**Correcciones a decisiones previas:**
- La nota del 2026-09-02 ("bug aislado 100% a la capa `xarm_api`/ROS2") era **incorrecta**: el bug
  está en el SDK C++ contra este firmware; ROS2 solo lo propaga. Descartados con esto los
  callejones: `id=8`, auto-colisión, conexiones concurrentes, `baud_checkset`, `report_type`,
  versión del SDK C++, y la hipótesis de "readiness" (3 llamadas en 90 s, siempre `ret=3`).
- Bug aparte, real y ya resuelto: `uf_software` se levantaba en red `bridge` (`172.17.0.2`) en vez de
  `--network host` (`docker start` reusa la config de red original del contenedor). Recreado con
  `docker rm -f uf_software` + `docker run --network host`, `robot_ip:=127.0.0.1` ya funciona. En
  bridge, el driver colgaba en `connect()` sin llegar a anunciar los servicios.

### Track elegido — cliente de servicios `/xarm/...` con enable tolerante a `ret=3`

Se **mantiene el driver oficial C++ `xarm_api`** (sirve para todo salvo el ACK cosmético).
`fred_lang_driver` NO envuelve `XArmAPI` de Python: es un cliente delgado de los servicios `/xarm/...`.

- [~] `fred_lang_driver/fred_arm.py`: clase `FredArm` sobre los servicios `/xarm/...`
  - [x] Paquete `fred_lang_driver` recreado limpio con `ros2 pkg create --build-type ament_python`
        (el paquete anterior no generaba `local_setup.bash` / plumbing rota)
  - [x] Helper `_make_client(srv_type, srv_name)` — crea cliente + espera + raise si no aparece
        (elimina la repetición del wait_for_service por cada servicio)
  - [x] `motion_enable(enable, id=8)` — validado en vivo: `ret=3` (cosmético) pero
        `/xarm/robot_states` reporta `mt_able=255`, `err=0`
  - [x] `set_mode(mode)` — validado, `ret=0`
  - [x] `set_state(state)` — validado, `ret=0`; el brazo llega a `state:2` (READY)
  - [x] `set_position(pose, speed, acc, wait)` — movimiento CARTESIANO validado: comandado
        subir Z 3cm, la pose del TCP cambió a z≈150.5, `ret=0`, `err=0`
  - [x] `set_servo_angle(angles, speed, acc, wait)` — movimiento ARTICULAR validado:
        comandado home (6 ceros), los ángulos volvieron a 0, `ret=0`, `err=0`
  - [x] Docstrings en los 5 métodos + docstring de clase (unidades marcadas: rad para
        angles; mm+rad para pose)
  - [ ] Suscripción a `/xarm/robot_states` + callback `_robot_states_cb` + `_servos_enabled()`
        (bitmask sobre `mt_able`)  ← SIGUIENTE
  - [ ] `enable()`: llama `motion_enable`; si `ret=3` NO aborta — verifica contra
        `/xarm/robot_states` (`mt_able`, `err == 0`)
- [ ] Primitivas de nivel medio: `home()`, `move_to()` / `move_joints()` que esperan `state == 2`
- [x] Limpiar `package.xml`: `xarm-python-sdk` eliminado y tag mal cerrado corregido
      (resuelto al recrear el paquete con `ros2 pkg create`)

### Track B (fallback, NO necesario ahora) — nodo propio envolviendo `XArmAPI` de Python

Solo si aparece un servicio que el driver C++ no pueda cumplir. Requeriría hornear
`xarm-python-sdk==1.18.4` en el Dockerfile.

### (opcional) Entender el ACK faltante a fondo
- [ ] `tcpdump` puerto 502: `motion_enable` de Python (`ret=0`) vs C++ (`ret=3`) — qué trama recibe
      uno y el otro no. No crítico para el deadline.

---

## Goal 3 — Integración de FrED-LANG con la API validada

- [ ] Conectar las funciones de alto nivel (`agarrar()`, `muevete_a()`, etc.) con `FredArm` (cliente de los servicios `/xarm/...`)
- [ ] Validar la capa de seguridad ROS2 (bloqueo de trayectorias imposibles) contra el driver elegido
- [ ] Prueba end-to-end: comando en lenguaje natural → código Python generado → ejecución validada en el simulador

---

## Goal 4 — Infraestructura futura (on the horizon, no bloqueante ahora)

- [ ] MoveIt2 como mejora futura para planeación más compleja
- [ ] Gazebo con físicas reales — pendiente de máquina con GPU dedicada
- [ ] Pipeline de generación de datos para entrenar el modelo VLA (fase 2 del proyecto)

---

## Notas rápidas / decisiones tomadas
- Prioridad de diseño: interpretabilidad (scripts Python legibles) y seguridad (validación ROS2 antes de mover el brazo real)
- MoveIt2 deliberadamente pospuesto para no añadir complejidad innecesaria en esta etapa
- **Cartesiano (`set_position`) es el flujo principal**; articular (`set_servo_angle`) se reserva
  para poses fijas como home. Razón: una cámara percibe coordenadas, no ángulos → cartesiano
  se alinea con el futuro VLA.
- `set_position` con `motion_type=0` (default) es lineal: si la pose no es alcanzable en línea
  recta o no tiene IK, falla con error C40. Útil como validación de seguridad implícita.
- Unidades: `angles` en radianes; `pose` = [x,y,z (mm), roll,pitch,yaw (rad)]. Nunca grados.
- Estados FIJADOS con `set_state` ≠ estados LEÍDOS en `/xarm/robot_states`. `set_state(0)` se
  reporta como `state:2` (READY). `set_state(0)` también limpia el código de error.
- `motion_enable` vía `/xarm/...` devuelve `ret=3` en el simulador — cosmético (SDK C++ ↔ firmware
  v2.4.0); los servos se habilitan y el brazo se mueve. `enable()` lo tratará como "verificar
  `/xarm/robot_states`", no como error.
- `uf_software` DEBE recrearse (`docker run --network host`), no solo `docker start`, o queda en
  red bridge y el driver no levanta.
- Al agregar un paquete nuevo al workspace, el **primer** `colcon build` debe ser completo (sin
  `--packages-select`); los builds parciales dejan el `setup.bash` raíz desincronizado y el paquete
  "invisible". `ros2 pkg executables <pkg>` es la verdad de fondo (no buscar archivos a mano).
- Un `package.xml` con XML malformado (p. ej. tag `</exec_depend>` mal cerrado) hace que `colcon
  build` termine "exitoso" pero instale el paquete a medias. Ante plumbing dudosa, recrear con
  `ros2 pkg create` es más rápido que depurarla.
- Ciclo de trabajo del nodo: **build → source → run**, siempre en la misma terminal.
