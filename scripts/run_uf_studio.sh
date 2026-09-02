#!/bin/bash
# Levanta el contenedor de UFACTORY Studio: el simulador de firmware que
# expone los servicios NATIVOS de xarm_api (/xarm/...). El launch de fake
# hardware / RViz2 NO expone estos servicios — solo
# xarm7_traj_controller/follow_joint_trajectory — por eso este contenedor es
# necesario aparte para probar la API nativa (set_position, set_servo_angle,
# gripper, etc.).
#
# Corre en un contenedor SEPARADO del contenedor de ROS2 Jazzy (fred-lang-jazzy).
# No se fusiona con el Dockerfile de este repo porque es una imagen ya
# construida por terceros, no parte del stack que compilamos nosotros.
#
# --network host es OBLIGATORIO (igual que en run_container.sh): sin esto,
# el contenedor de ROS2 Jazzy no puede alcanzar los puertos del protocolo
# xArm (30000-30003) ni la UI web en el puerto 18333.

set -e

IMAGE_NAME="danielwang123321/uf-ubuntu-docker"
CONTAINER_NAME="uf_software"
DOF=7   # grados de libertad del xArm (usamos xArm7)
AXIS=7  # segundo argumento de xarm_start.sh — mismo valor que DOF

# Si el contenedor ya existe (de una corrida anterior), lo reutilizamos en
# vez de fallar con "name already in use".
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "El contenedor '$CONTAINER_NAME' ya existe. Reiniciándolo..."
  docker start -ai "$CONTAINER_NAME"
  exit 0
fi

echo "Creando el contenedor '$CONTAINER_NAME' desde $IMAGE_NAME..."
docker run -it \
  --name "$CONTAINER_NAME" \
  --network host \
  "$IMAGE_NAME" \
  /bin/bash -c "/xarm_scripts/xarm_start.sh $DOF $AXIS; exec /bin/bash"

# xarm_start.sh levanta DOS sesiones de `screen` en segundo plano:
#   1. el binario del firmware simulado
#   2. el daemon web (xarmdaemon), que sirve UFACTORY Studio en el puerto 18333
#
# Una vez dentro del contenedor (te quedas en un bash normal tras el arranque):
#   screen -ls              # confirmar que ambas sesiones están corriendo
#   screen -r <nombre>      # ver logs de una sesión (Ctrl+A, D para salir sin matarla)
#
# UFACTORY Studio queda accesible en el HOST en: http://localhost:18333
