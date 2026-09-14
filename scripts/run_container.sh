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
CONTAINER_NAME="fred-lang-jazzy"

# Permite que contenedores locales de Docker se conecten al X server del host.
# Esto se resetea cada sesión nueva de terminal/reinicio, por eso va aquí y no
# es un paso "de una sola vez".
xhost +local:docker

# Borra cualquier contenedor previo con el mismo nombre (colgado de una sesión
# anterior) para que --name no falle con "name already in use". Como corremos
# con --rm, en el caso normal no queda nada que borrar; esto cubre el caso de
# un cierre sucio.
docker rm -f "$CONTAINER_NAME" 2>/dev/null || true

docker run -it --rm \
  --name "$CONTAINER_NAME" \
  --network host \
  --device /dev/dri \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "$REPO_ROOT/src:/root/xarm_ws/src" \
  "$IMAGE_NAME"
