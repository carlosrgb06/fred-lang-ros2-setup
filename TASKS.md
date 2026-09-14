# FrED-LANG — Goals & Tasks

> Última actualización: 2026-09-13
> Deadline del entregable: ~3 semanas desde finales de agosto 2026

Convención de estado: `[ ]` pendiente · `[x]` hecho · `[~]` en progreso · `[!]` bloqueado

> **Nota de modelo:** el proyecto usa **xArm6** (6 DOF). Firmware con
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
- [x] Agregar el contenedor de UFACTORY Studio (`uf-ubuntu-docker`) al repo
  - Contenedor separado (no se fusiona con el de ROS2 Jazzy)
  - Documentado en el README el comando de arranque correcto
  - Script `run_uf_studio.sh` que automatiza el arranque

---

## Goal 2 — Simulador nativo del xArm6 funcionando end-to-end ✅

- [x] Decidido: usar API nativa de xArm (`xarm_api`) en vez de MoveIt2 por ahora
- [x] Contenedor `uf_software` corriendo en `--network host`
- [x] Firmware simulado arrancado correctamente como xArm6 (`xarm_start.sh 6 6`)
- [x] Driver `xarm_api` lanzado (`xarm6_driver.launch.py robot_ip:=127.0.0.1`)
- [x] Servicios nativos `/xarm/...` confirmados con `ros2 service list`
- [x] Verificado: `motion_enable` + `set_mode` + `set_state` + `set_position` → el brazo se mueve
- [x] **RESUELTO — el `ret=3` de `motion_enable` es cosmético.** Análisis abajo.
- [!] UFACTORY Studio (`localhost:18333`): abandonado como vía. La GUI web no conecta al
      firmware sim. No bloqueante — es solo visualización; se sigue sin él.

### Diagnóstico del `ret=3` de `motion_enable` (2026-09-03)

**Causa raíz:** el SDK **C++ v1.18.1** (el que compila `xarm_api`) espera de forma bloqueante una
trama de respuesta al opcode `MOTION_EN` (11) con el transaction-id correcto. El firmware **v2.4.0**
del simulador **nunca envía esa trama** (probado esperando hasta 20 s con `set_timeout(20)`: sigue
`ret=3`). El resto de opcodes (`SET_MODE`, `SET_STATE`, `MOVE_LINE`) responden normal. El SDK
**Python 1.18.4** no depende de ese ACK → por eso ahí da `ret=0`.

**Es cosmético, no funcional.** Probado con un binario C++ mínimo:
- `motion_enable` → `ret=3`, pero `motor_enable_states = [1,1,...]` → los servos SÍ se habilitan
- `set_mode(0)` / `set_state(0)` → `ret=0`
- `set_position` → `ret=0`; ángulos de joints y TCP cambian → el brazo se mueve de verdad

**Correcciones a decisiones previas:**
- La nota del 2026-09-02 ("bug aislado 100% a la capa `xarm_api`/ROS2") era **incorrecta**: el bug
  está en el SDK C++ contra este firmware; ROS2 solo lo propaga. Descartados: `id=8`, auto-colisión,
  conexiones concurrentes, `baud_checkset`, `report_type`, versión del SDK C++, y "readiness".
- Bug aparte, real y ya resuelto: `uf_software` se levantaba en red `bridge` en vez de
  `--network host` (`docker start` reusa la config de red original). Recreado con
  `docker rm -f` + `docker run --network host`, `robot_ip:=127.0.0.1` ya funciona.

---

## Goal 2.5 — Librería FredArm, Capa 1 (control de bajo nivel) ✅

Se **mantiene el driver oficial C++ `xarm_api`**. `fred_lang_driver` NO envuelve `XArmAPI`
de Python: es un cliente delgado de los servicios `/xarm/...`.

- [x] Paquete `fred_lang_driver` recreado limpio con `ros2 pkg create --build-type ament_python`
- [x] Helper `_make_client(srv_type, srv_name)` — crea cliente + espera + raise si no aparece
- [x] **Arranque:**
  - [x] `motion_enable(enable, id=8)` — `ret=3` cosmético; servos habilitados (`mt_able=255`)
  - [x] `set_mode(mode)` — `ret=0`
  - [x] `set_state(state)` — `ret=0`; brazo llega a `state:2` (READY)
- [x] **Movimiento:**
  - [x] `set_position(pose, speed, acc, wait)` — CARTESIANO validado (subió Z 3cm, `ret=0`)
  - [x] `set_servo_angle(angles, speed, acc, wait)` — ARTICULAR validado (home, `ret=0`)
  - [x] `move_gohome(speed, acc, wait)` — home de fábrica validado (regresa a `[0,...]`, `ret=0`)
- [x] **Lectura de estado:**
  - [x] Suscripción a `/xarm/robot_states` (QoS RELIABLE+VOLATILE = default, profundidad 10)
  - [x] `_robot_states_cb` guarda el último mensaje en `_last_state`
  - [x] `hay_error()` — chequea `err != 0`
  - [x] `servos_ok(num_joints=6)` — bitmask sobre `mt_able` (máscara de 6 bits)
  - [x] `esperar_listo(timeout)` — bloquea con `spin_once` hasta READY + sin error + servos ok
  - [x] `get_angulos()` — lee `_last_state.angle` (sin servicio, gratis)
- [x] **Recuperación:**
  - [x] `clean_error()` — tipo `Call` (request vacío); `ret=0`
- [x] Docstrings en todos los métodos + docstring de clase (unidades marcadas)
- [x] `package.xml` limpio (`xarm-python-sdk` eliminado, tag mal cerrado corregido al recrear)

**Verificación end-to-end (2026-09-13):** `main()` de prueba ejecuta arranque → `get_angulos`
inicial → `set_position` → `get_angulos` (ángulos cambian) → `move_gohome` → `get_angulos`
(vuelven a 0) → `clean_error`. Todos los pasos con `ret=0`/`err=0` y `esperar_listo()` confirmando.

---

## Goal 3 — Capa 3: primitivas de alto nivel + integración FrED-LANG

- [ ] Primitivas de alto nivel que envuelven la Capa 1 con `esperar_listo()` integrado y
      retornan True/False. Conjunto mínimo propuesto:
  - [ ] `preparar()` — secuencia de arranque completa en una llamada
  - [ ] `home()` — envuelve `move_gohome` + verificación
  - [ ] `mover_a(x, y, z, ...)` — envuelve `set_position` + verificación (el caballo de batalla)
  - [ ] `mover_juntas(angles)` — envuelve `set_servo_angle` + verificación
- [ ] Nodo orquestador + `exec()` del código generado por el LLM (Code as Policies)
- [ ] Validar la capa de seguridad ROS2 (bloqueo de trayectorias imposibles)
- [ ] Prueba end-to-end: comando en lenguaje natural → código Python generado → ejecución validada

### Pinza / gripper — pendiente de hardware
- El simulador `uf_software` levanta el firmware sin actuador, así que NO expone servicios
  de gripper. Hipótesis confirmada: aparecen al conectar un actuador real.
- **Hallazgo útil:** los servicios de gripper Lite6 (`open_lite6_gripper`,
  `close_lite6_gripper`, `stop_lite6_gripper`, `clean_gripper_error`) usan el tipo `Call`
  (request vacío) — mismo molde que `clean_error()`. Cuando haya pinza, `agarrar()`/`soltar()`
  serán triviales de implementar.
- [ ] Averiguar cómo levantar el firmware del sim con un actuador/gripper declarado.
- [ ] Implementar `agarrar()` / `soltar()` cuando el actuador esté disponible.

---

## Goal 4 — Infraestructura futura (no bloqueante ahora)

- [ ] MoveIt2 como mejora futura para planeación más compleja
- [ ] Gazebo con físicas reales — pendiente de máquina con GPU dedicada
- [ ] Pipeline de generación de datos para entrenar el modelo VLA (fase 2)

---

## Documentación
- [~] Manual del proyecto (`MANUAL.md`) — "un README pero mejor", guía para futuros devs.
      En construcción: empezando por la sección 4 (la librería `FredArm`).
- [x] README y TASKS actualizados a xArm6 + Capa 1 completa

---

## Notas rápidas / decisiones tomadas
- Prioridad de diseño: interpretabilidad (scripts Python legibles) y seguridad (validación ROS2 antes de mover)
- MoveIt2 deliberadamente pospuesto para no añadir complejidad innecesaria en esta etapa
- **Diseño en dos niveles:** Capa 1 (servicios directos, siempre disponibles para el LLM) +
  Capa 3 (primitivas de alto nivel que el LLM usará mayormente). Las de alto nivel encapsulan
  secuencias validadas → seguridad; se leen como recetas → interpretabilidad.
- **Cartesiano (`set_position`) es el flujo principal**; articular (`set_servo_angle`) se reserva
  para poses fijas como home. Razón: una cámara percibe coordenadas, no ángulos → cartesiano
  se alinea con el futuro VLA.
- `wait=True` en un movimiento solo garantiza que TERMINÓ, no que terminó BIEN. `esperar_listo()`
  verifica READY + sin error + servos ok → es la red de seguridad tras cada comando.
- Una suscripción solo recibe mensajes mientras algo hace spin. `esperar_listo()` usa
  `spin_once` en su loop para refrescar `_last_state` mientras espera.
- `get_angulos()` lee de la suscripción, NO llama a `/xarm/get_servo_angle` — el dato ya llega
  por el tópico; pedirlo por servicio sería redundante.
- `set_position` con `motion_type=0` (default) es lineal: si la pose no es alcanzable en línea
  recta o no tiene IK, falla con error C40. Útil como validación de seguridad implícita.
- Unidades: `angles` en radianes; `pose` = [x,y,z (mm), roll,pitch,yaw (rad)]. Nunca grados.
- Estados FIJADOS con `set_state` ≠ estados LEÍDOS en `/xarm/robot_states`. `set_state(0)` se
  reporta como `state:2` (READY) y además limpia el código de error.
- `uf_software` DEBE recrearse (`docker run --network host`), no solo `docker start`.
- Primer `colcon build` de un paquete nuevo SIEMPRE completo (sin `--packages-select`);
  `ros2 pkg executables <pkg>` es la verdad de fondo de si ROS2 lo ve.
- `package.xml` con XML malformado → `colcon build` "exitoso" pero paquete a medias. Recrear
  con `ros2 pkg create` es más rápido que depurar.
- QoS de una suscripción debe coincidir con el publisher o el callback no dispara. `robot_states`
  es RELIABLE+VOLATILE (default), basta pasar profundidad 10.
- Ciclo de trabajo del nodo: **build → source → run**, siempre en la misma terminal.
