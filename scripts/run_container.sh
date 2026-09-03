#!/bin/bash
# Levanta el contenedor fred-lang-jazzy con todo lo necesario para X11 (RViz2)
# y acceso al dispositivo gráfico del host (necesario incluso para RViz2, no
# solo para Gazebo — sin esto Mesa no puede inicializar ningún driver).

set -e

# Calcula la ruta del repo a partir de dónde vive ESTE script, no de dónde
# estabas parado al llamarlo — así "cd scripts && ./run_container.sh" y
# "./scripts/run_container.sh" desde la raíz dan exactamente el mismo mount.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

IMAGE_NAME="fred-lang-jazzy"

# Permite que contenedores locales de Docker se conecten al X server del host.
# Esto se resetea cada sesión nueva de terminal/reinicio, por eso va aquí y no
# es un paso "de una sola vez".
xhost +local:docker

docker run -it --rm \
  --network host \
  --device /dev/dri \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "$REPO_ROOT/src:/root/xarm_ws/src" \
  "$IMAGE_NAME"
