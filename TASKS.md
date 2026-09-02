# FrED-LANG — Goals & Tasks

> Última actualización: 2026-09-02
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
- [x] Verificado con SDK de Python directo: `motion_enable` + `set_mode` + `set_state` + `set_position` → el brazo se mueve en Studio 🎉
- [!] **Bloqueado vía ROS2:** `motion_enable` regresa `ret=3` (timeout) al llamarlo desde `xarm_api`/ROS2, aunque el firmware está sano (confirmado por SDK Python)
  - Descartado: `id=8` vs joints individuales
  - Descartado: auto-colisión / estado corrupto del brazo
  - Descartado: conexiones TCP concurrentes (solo 1 cliente activo)
  - Descartado: `baud_checkset:=false`
  - Descartado: `report_type:=rich`
  - Descartado: versión del SDK C++ desactualizada — `v1.18.1` ya es la última tag publicada y coincide con el tip de `master`, no hay versión más nueva a la que subir
  - **Decisión (2026-09-02): se abandona Track A.** El SDK de Python (`xarm-python-sdk==1.18.4`) funciona perfecto contra el mismo firmware en el mismo momento (`motion_enable`/`set_mode`/`set_state`/`set_position` todos con `ret=0`, brazo se mueve en Studio) — el bug está aislado 100% a la capa `xarm_api`/ROS2, no al firmware ni al SDK. No vale la pena seguir persiguiéndolo con el deadline encima.

### Track A — Fix de raíz: actualizar SDK C++ de `xarm_api` — **DESCARTADO**
- [x] Crear branch `test/sdk-upgrade`
- [x] Confirmar que no hay versión más nueva del SDK C++ a la que subir (`v1.18.1` = tip de `master`)
- [x] Aislar el bug: SDK de Python funciona, `xarm_api`/ROS2 no — mismo firmware, mismo instante
- Se documenta y se descarta. No se sigue esta ruta.

### Track B — Camino elegido: nodo propio con SDK de Python
- [ ] Crear paquete ROS2 nuevo `fred_lang_driver`
- [ ] Nodo `rclpy` que envuelva `XArmAPI` (Python) internamente
- [ ] Exponer servicios equivalentes: `motion_enable`, `set_mode`, `set_state`, `set_position`, `set_servo_angle`
- [ ] Definir si reemplazan los nombres `/xarm/...` o usan namespace propio mientras se prueba
- [ ] Probar el flujo completo de habilitar + mover desde este nodo
- [ ] Hornear `xarm-python-sdk==1.18.4` en el Dockerfile (falta mergear a la rama principal)

---

## Goal 3 — Integración de FrED-LANG con la API validada

- [ ] Conectar las funciones de alto nivel (`agarrar()`, `muevete_a()`, etc.) con los servicios nativos verificados (de Track A o B)
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
- Tracks A y B corren en paralelo — B es el camino rápido para desbloquear el deadline, A es el fix correcto a mediano plazo
