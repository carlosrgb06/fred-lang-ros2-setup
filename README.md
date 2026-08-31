# FrED-LANG — Setup del stack ROS2 / xArm (gemelo digital)

Repositorio para el sistema de FrED Lang: control del brazo UFACTORY xArm vía
lenguaje natural (arquitectura Code as Policies). Este repo empaqueta todo el
entorno de ROS2 + xArm en una imagen Docker — clonar y `docker build` es
suficiente, no hace falta instalar ROS2 ni compilar nada a mano.

## Prerrequisitos

- Docker instalado (`docker --version` para confirmar)
- Para gráficos (RViz2, Gazebo): X11 corriendo en el host (normal en
  cualquier escritorio de Ubuntu) y acceso al dispositivo `/dev/dri`
- **No se necesita `docker compose`** — este repo usa `docker build` /
  `docker run` directo. Si tu instalación de Docker no trae el plugin de
  compose (`docker: unknown command: docker compose`), no es necesario
  instalarlo para seguir esta guía.

## Setup desde cero

### 1. Clonar el repo con el submodule de xarm_ros2

```bash
git clone --recursive https://github.com/carlosrgb06/fred-lang-ros2-setup.git
cd fred-lang-ros2-setup
```

Si ya lo clonaste sin `--recursive`:

```bash
git submodule update --init --recursive
```

### 2. Construir la imagen

```bash
docker build -t fred-lang-jazzy .
```

Esto compila `xarm_ros2` completo (incluyendo `xarm_gazebo`) dentro de la
imagen. Tarda varios minutos la primera vez. **Nota importante:** `xarm_gazebo`
se compila siempre, sin importar si la máquina tiene GPU o no — compilar
código no requiere aceleración gráfica, solo *ejecutar* Gazebo con render sí
la necesita. Además, `xarm_moveit_config` depende de `xarm_gazebo`, así que
saltar su compilación rompe el build completo.

### 3. Correr el contenedor

```bash
./scripts/run_container.sh
```

Este script hace tres cosas por ti:
- `xhost +local:docker` — permite que contenedores locales se conecten al
  X server del host (se resetea cada sesión nueva, por eso el script lo
  corre cada vez)
- Pasa `--device /dev/dri` — **esto es indispensable incluso solo para
  RViz2**, no únicamente para Gazebo. Sin acceso al dispositivo gráfico,
  Mesa no puede inicializar ningún driver y los procesos gráficos se quedan
  colgados sin abrir ventana ni mostrar error claro en el log de ROS.
- Monta `/tmp/.X11-unix` y pasa `$DISPLAY` para que las ventanas se puedan
  dibujar en tu escritorio

Si prefieres correrlo manualmente sin el script:

```bash
xhost +local:docker

docker run -it --rm \
  --network host \
  --device /dev/dri \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  fred-lang-jazzy
```

## Uso diario

Ya dentro del contenedor, ROS2 y el workspace ya vienen sourceados
automáticamente (vía `scripts/entrypoint.sh`).

### Simulación fake (cinemática, sin física — RViz2 + MoveIt2)

```bash
ros2 launch xarm_moveit_config xarm7_moveit_fake.launch.py
```

### Inspección en vivo

```bash
ros2 topic list
ros2 node list
ros2 topic echo /joint_states          # ángulos en espacio articular, NO cartesiano
ros2 run tf2_ros tf2_echo link_base link_eef   # pose cartesiana del efector final
ros2 control list_controllers
```

## Arquitectura del gemelo digital

```
URDF / Xacro  →  MoveIt2  →  ros2_control  →  Gazebo Sim (simulación física)
                                            └→ xArm driver (hardware real)
```

`ros2_control` es la capa de abstracción clave: expone la misma interfaz de
"hardware" sin importar si abajo hay un simulador o el robot físico. El mismo
código de MoveIt2 funciona igual en fake, en Gazebo, y eventualmente en el
xArm real — solo cambia qué hay conectado del otro lado de `ros2_control`.

RViz2 es **solo un visualizador** — dibuja lo que los tópicos le dicen, sin
física de por medio. Gazebo sí corre un motor de física real (gravedad,
colisiones, inercia) y expone esa simulación a `ros2_control` como si fuera
el driver real del robot.

## Troubleshooting

| Problema | Causa | Solución |
|---|---|---|
| `docker: unknown command: docker compose` | El plugin de compose no viene instalado en esta versión de Docker | No es necesario — usar `docker build`/`docker run` directo, como en este README |
| `E: Unable to locate package ...` durante `rosdep install` en el Dockerfile | Cada `RUN` es una capa aislada; un `apt-get update` anterior no persiste a la siguiente capa | Agregar `apt-get update` en el mismo `RUN` justo antes de `rosdep install` |
| `Failed to find ... xarm_gazebo/package.sh` al compilar `xarm_moveit_config` | Se saltó la compilación de `xarm_gazebo` (`--packages-skip`), pero `xarm_moveit_config` depende de él | Compilar `xarm_gazebo` siempre — no requiere GPU para compilar, solo para ejecutarse |
| RViz2 no abre ventana, pero `ros2 node list` muestra `/rviz2` corriendo | Falta acceso al dispositivo gráfico del host | Agregar `--device /dev/dri` al `docker run` |
| `MESA: error: Failed to query drm device` / `failed to load driver: iris` | Mismo problema de arriba — Mesa no puede inicializar sin `/dev/dri` | Igual, `--device /dev/dri` |
| Docker socket permission denied | Falta reboot completo tras `usermod -aG docker` | Reboot, no solo logout/login |
| `git push` pide usuario/contraseña y falla | GitHub ya no soporta autenticación por password | Configurar SSH (`git remote set-url origin git@github.com:...`) o usar un token |

## Pendientes / próximos pasos

- [ ] Confirmar DOF real del xArm físico (6 vs 7) cuando haya acceso al hardware
- [ ] Explorar espacio cartesiano con `tf2_echo` (joint-space vs Cartesian-space)
- [ ] Probar `xarm7_moveit_gazebo.launch.py` en una compu con GPU dedicada
- [ ] Capa de motion primitives + integración con el pipeline LLM (Code as Policies)
- [ ] Conectar el driver real del xArm cuando el hardware esté disponible

## Notas de lectura del SDK del xArm

Orden recomendado dentro del SDK oficial:
1. `README`
2. Máquina de modos/estados en `xarm_api.md`
3. Códigos de error en `xarm_api_code.md`
4. Ejemplos numerados en `example/wrapper/common/`

(Los `< >` en la documentación de comandos son solo notación, no caracteres literales.)
