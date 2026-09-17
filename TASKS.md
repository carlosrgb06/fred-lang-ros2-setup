# FrED-LANG — Goals & Tasks

> Última actualización: 2026-09-16
> Entregable 1 (Capa 1 + Capa 3 de la librería FredArm) cumplido — siguiente fase: orquestador + integración LLM

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
  - [x] `motion_enable(enable, id=8)` — `ret=3` cosmético; servos habilitados (`mt_able=63`)
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
  - [x] `esperar_listo(timeout)` → renombrado a `estado_ok(timeout)` — bloquea con `spin_once` hasta READY + sin error + servos ok (confirmación tras un movimiento)
  - [x] `verificar_listo()` — precondición: un solo `spin_once` y lanza `FredArmError` si el brazo no está listo *ahora* (distingue `_last_state is None` de no-READY)
  - [x] `get_angulos()` — lee `_last_state.angle` (sin servicio, gratis)
- [x] **Recuperación:**
  - [x] `clean_error()` — tipo `Call` (request vacío); `ret=0`
- [x] **Casteo defensivo de tipos:** todos los `request` castean sus campos al tipo que ROS2
      exige (`float()` en poses/ángulos/velocidades, `int()` en arranque). Evita el
      `Aborted (core dumped)` que provoca un `int` donde el mensaje espera `float`.
- [x] Docstrings en todos los métodos + docstring de clase (unidades marcadas)
- [x] `package.xml` limpio (`xarm-python-sdk` eliminado, tag mal cerrado corregido al recrear)

**Verificación end-to-end (2026-09-13):** `main()` de prueba ejecuta arranque → `get_angulos`
inicial → `set_position` → `get_angulos` (ángulos cambian) → `move_gohome` → `get_angulos`
(vuelven a 0) → `clean_error`. Todos los pasos con `ret=0`/`err=0` y `estado_ok()` confirmando.

---

## Goal 3 — Capa 3: primitivas de alto nivel + integración FrED-LANG

### Primitivas de alto nivel ✅

Envuelven la Capa 1 con verificación integrada. **Corrección al plan original:** NO
retornan True/False — **lanzan `FredArmError`** ante cualquier fallo (fallar ruidoso y
detenerse); la ausencia de excepción es la señal de éxito. Esto encaja con el flujo del
orquestador: la primitiva *lanza*, el orquestador *atrapa y traduce a feedback para el LLM*.
Todas siguen el patrón: `validar args → verificar_listo() → ejecutar Capa 1 → comprobar ret
→ confirmar con estado_ok()`.

- [x] `preparar()` — secuencia de arranque completa en una llamada (`motion_enable →
      set_mode → set_state → estado_ok`) con validación de `enable`
- [x] `recuperar()` — `clean_error()` + `preparar()`; saca al brazo de un error y lo
      re-arranca. Dos niveles de detección: fallo de comunicación (`ret` de clean_error) y
      fallo de efecto (no vuelve a READY)
- [x] `home()` — envuelve `move_gohome` + verificación
- [x] `mover_a(x, y, z, roll, pitch, yaw, ...)` — envuelve `set_position` (el caballo de
      batalla). Coordenadas nombradas; orientación por defecto "efector hacia abajo"
- [x] `mover_servos_a(angulos, num_joints=6, ...)` — envuelve `set_servo_angle`; valida
      cantidad de ángulos contra `num_joints` y tipo de cada uno
- [x] Helper `verificar_listo()` — precondición reusable (DRY) al inicio de cada primitiva
- [x] Clase de excepción propia `FredArmError` en `fred_arm_error.py`

### Pendiente en Capa 3 / integración

- [ ] Actualizar el `main()` de ejemplo para consumir las primitivas dentro de un
      `try/except FredArmError` (ensayo del patrón del orquestador)
- [ ] Nodo orquestador + `exec()` del código generado por el LLM (Code as Policies).
      Un solo `FredArm` vivo toda la sesión (reutilizado por comando); envuelve `exec()` en
      `try/except FredArmError` y devuelve el mensaje al LLM. Decidir: ¿quién llama
      `recuperar()` entre comandos fallidos?
- [ ] Validar la capa de seguridad ROS2 (bloqueo de trayectorias imposibles)
- [ ] Prueba end-to-end: comando en lenguaje natural → código Python generado → ejecución validada

### Migración a hardware real — checklist del lab

Diagnóstico a hacer *en el lab, antes de mover el brazo físico*. La portabilidad es 1:1
(solo cambia `robot_ip`), pero hay que confirmar compatibilidad y seguridad primero:

- [ ] Conectividad: IP del controlador y IP estática en la interfaz del host (conexión
      directa por ethernet no trae DHCP)
- [ ] Localizar y probar el **E-stop físico** del control box ANTES de correr cualquier script
- [ ] Leer la versión de firmware real (UFACTORY Studio de escritorio conecta al hardware
      real, a diferencia del sim) y compararla contra el sim (**v2.4.0**) y contra la matriz
      de compatibilidad del SDK C++ (`xArm-CPLUS-SDK`, sin cambios recientes = estable)
- [ ] Primer contacto: solo arranque (`preparar()`) a **velocidad mínima**, sin movimiento,
      para ver si aparece algún `ret` raro antes de que nada se mueva
- [ ] Confirmar en real si el `ret=3` de `motion_enable` sigue siendo cosmético o indica un
      fallo real de habilitación (ver `# REVISAR EN HARDWARE REAL` en el código)
- [ ] Verificar el número de DOF: `robot_states.angle` debe tener 6 elementos (el campo
      `DETAIL: 7,7` del sim quedó sin confirmar qué significa — revisar el parseo del SDK)
- [ ] Configurar TCP/payload si hay gripper o herramienta montada (cambia la IK cartesiana)

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
      Secciones 1–5 hechas; faltan 6 (guía de uso), 7 (trabajo futuro), 8 (referencias).
- [x] README y TASKS actualizados a xArm6 + Capa 1 + Capa 3 completas

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
- `wait=True` en un movimiento solo garantiza que TERMINÓ, no que terminó BIEN. `estado_ok()`
  verifica READY + sin error + servos ok → es la red de seguridad tras cada comando.
- Dos verificaciones con propósito distinto: `estado_ok()` **espera** (loop de spin, tras un
  movimiento) vs `verificar_listo()` **mira una vez** (precondición, antes de mover). Comparten
  forma, no intención → métodos separados a propósito.
- Una suscripción solo recibe mensajes mientras algo hace spin. Ambas verificaciones usan
  `spin_once` para refrescar `_last_state`; por eso `_last_state` puede ser `None` si nunca se
  spineó (= no se corrió `preparar()`).
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
- **Manejo de errores:** el sistema falla ruidoso y se detiene (`FredArmError`), reportando qué
  falló para que el LLM corrija. Capa 1 devuelve `ret` crudo (no lanza); Capa 3 traduce a
  excepción. La validación de tipos vive en Capa 3 (frontera con el LLM); el casteo a float, en
  Capa 1 (frontera con ROS2).
- **Recuperación de errores (confirmado experimentalmente):** una pose imposible sobre brazo
  limpio da `ret` negativo, `err=0`, `state=1`; sobre brazo ya en error da `ret=1`, `state=4`,
  `err=21` (familia planificación/cinemática). La secuencia que recupera es `clean_error()` +
  arranque completo (= `recuperar()`). `clean_error()` solo NO baja el `err=21` en este firmware
  (da `ret=0` sin limpiar). La confirmación real viene de `estado_ok()`, no del `ret`.
- **Trampa de las dos tablas:** UFACTORY tiene dos tablas de códigos con números chicos — el
  `ret` de la API (donde 21 = modbus baudrate) y el `err` del controlador (donde 21 =
  planificación). El `err=21` de `FredArm` es el segundo. No confundir `ret` con `err`.
- El estado del brazo persiste entre ejecuciones del script: reiniciar el contenedor del sim
  para experimentos limpios.
