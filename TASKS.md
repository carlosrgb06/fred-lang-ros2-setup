# FrED-LANG — Goals & Tasks

> Última actualización: 2026-09-07
> Deadline del entregable: ~3 semanas desde finales de agosto 2026

Convención de estado: `[ ]` pendiente · `[x]` hecho · `[~]` en progreso · `[!]` bloqueado

---

## Goal 1 — Entorno de desarrollo reproducible ✅

- [x] Repo `carlosrgb06/fred-lang-ros2-setup` publicado
- [x] Contenedor ROS2 Jazzy (vía rocker) con `xarm_ros2` (branch `jazzy`) como submódulo
- [x] Fix de Dockerfile: `apt-get update` en el mismo layer que los installs
- [x] `/dev/dri` pasado al contenedor para render de RViz2
- [ ] Habilitar a un colaborador a replicar el entorno completo
  - [!] Bloqueado: issue de `docker buildx` en su máquina — pendiente de resolver
- [X] Agregar el contenedor de UFACTORY Studio (`uf-ubuntu-docker`) al repo `fred-lang-ros2-setup`
  - Puede quedar como contenedor separado (no necesita fusionarse con el de ROS2 Jazzy)
  - Documentar en el README el comando de arranque correcto: `docker run -it --name uf_software --network host danielwang123321/uf-ubuntu-docker /bin/bash` + `/xarm_scripts/xarm_start.sh 7 7`
  - Idealmente un script (`run_uf_studio.sh`) que automatice esto para no repetir el comando a mano cada vez

---

## Goal 2 — Simulador nativo del xArm7 funcionando end-to-end

- [x] Decidido: usar API nativa de xArm (`xarm_api`) en vez de MoveIt2 por ahora
- [x] Contenedor `uf_software` (UFACTORY Studio simulator) corriendo en `--network host`
- [x] Firmware simulado arrancado correctamente como xArm7 (`xarm_start.sh 7 7`)
- [x] UFACTORY Studio accesible en `localhost:18333`, robot conectado y visible
- [x] Driver `xarm_api` lanzado (`xarm7_driver.launch.py robot_ip:=127.0.0.1`)
- [x] Servicios nativos `/xarm/...` confirmados con `ros2 service list`
- [x] Verificado con SDK de Python directo: `motion_enable` + `set_mode` + `set_state` + `set_position` → el brazo se mueve
- [x] **RESUELTO — el `ret=3` de `motion_enable` es cosmético.** Análisis abajo.
- [X] UFACTORY Studio (`localhost:18333`) no carga la web ahora mismo; el firmware y los puertos 30001-30003 sí responden. No bloqueante (Studio es solo visualización). Pendiente: revisar `xarmdaemon` dentro de `uf_software`.

### Diagnóstico del `ret=3` de `motion_enable` (2026-09-03)

**Causa raíz:** el SDK **C++ v1.18.1** (el que compila `xarm_api`) espera de forma bloqueante una
trama de respuesta al opcode `MOTION_EN` (11) con el transaction-id correcto. El firmware **v2.4.0**
del simulador **nunca envía esa trama** (probado esperando hasta 20 s con `set_timeout(20)`: sigue
`ret=3`). El resto de opcodes (`SET_MODE`, `SET_STATE`, `MOVE_LINE`) responden normal. El SDK
**Python 1.18.4** no depende de ese ACK → por eso ahí da `ret=0`.

**Es cosmético, no funcional.** Probado con un binario C++ mínimo sin ROS2 ni el hilo de
`/joint_states` (`xarm_sdk/cxx/example/9999-fredlang_enable_probe.cc`):
- `motion_enable` → `ret=3`, pero `motor_enable_states = [1,1,1,1,1,1,1]` → los 7 servos SÍ se habilitan
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
- [~] `fred_lang_driver/fred_arm.py`: clase helper `FredArm` sobre `/xarm/motion_enable`, `/xarm/set_mode`,
      `/xarm/set_state`, `/xarm/set_position`, `/xarm/set_servo_angle`
  - [x] Paquete `fred_lang_driver` recreado limpio con `ros2 pkg create --build-type ament_python`
        (el paquete anterior no generaba `local_setup.bash` / plumbing rota)
  - [x] `motion_enable(enable, id=8)` — cliente de `/xarm/motion_enable`, patrón
        `call_async` + `spin_until_future_complete`; entry point registrado, `ros2 run` OK
  - [x] Verificado en vivo desde `FredArm`: `motion_enable(1)` → `ret=3` (cosmético) pero
        `/xarm/robot_states` reporta `mt_able=255`, `err=0` → los 7 servos habilitados
  - [ ] `set_mode(mode)` y `set_state(state)` (mismo molde, tipo `SetInt16` sin `id`)
  - [ ] `set_position` / `set_servo_angle`
- [ ] `enable()`: llama `motion_enable`; si devuelve `ret=3` (RES_TIMEOUT) NO aborta — verifica contra
      el tópico `/xarm/robot_states` (`mt_able` = máscara de servos activos, `err == 0`)
  - [ ] Requiere primero la suscripción a `/xarm/robot_states` + callback `_robot_states_cb` + `_servos_enabled()` (bitmask sobre `mt_able`)
- [ ] `move_to()` / `move_joints()`: envuelven `set_position` / `set_servo_angle`, esperan `state == 2`
- [ ] Smoke test: habilitar + mover desde este helper
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
- `motion_enable` vía `/xarm/...` devuelve `ret=3` en el simulador — es cosmético (SDK C++ ↔ firmware v2.4.0),
  los servos se habilitan y el brazo se mueve. `FredArm.enable()` lo trata como "verificar `/xarm/robot_states`", no como error.
- `uf_software` DEBE recrearse (`docker run --network host`), no solo `docker start`, o queda en red bridge y el driver no levanta.
- Al agregar un paquete nuevo al workspace, el **primer** `colcon build` debe ser completo (sin `--packages-select`); los builds parciales dejan el `setup.bash` raíz desincronizado y el paquete "invisible". `ros2 pkg executables <pkg>` es la verdad de fondo para saber si ROS2 lo ve (no buscar archivos a mano).
- Un `package.xml` con XML malformado (p. ej. tag `</exec_depend>` mal cerrado) hace que `colcon build` termine "exitoso" pero instale el paquete a medias. Ante plumbing dudosa, recrear con `ros2 pkg create` es más rápido que depurarla.
