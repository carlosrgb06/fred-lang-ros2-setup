FROM osrf/ros:jazzy-desktop

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy

RUN apt-get update && apt-get install -y \
    python3-colcon-common-extensions \
    python3-rosdep \
    git \
    ros-${ROS_DISTRO}-moveit \
    ros-${ROS_DISTRO}-ros-gz-sim \
    ros-${ROS_DISTRO}-ros-gz-bridge \
    ros-${ROS_DISTRO}-gz-ros2-control \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /root/xarm_ws/src
WORKDIR /root/xarm_ws

# xarm_ros2 viene como git submodule del propio repo (ver README), por lo que
# se copia del contexto de build en vez de clonarse aquí. Esto fija la versión
# exacta registrada en el submodule.
COPY src/xarm_ros2 /root/xarm_ws/src/xarm_ros2

# apt-get update es indispensable aquí: cada RUN es una capa aislada, y el
# 'rm -rf /var/lib/apt/lists/*' del paso anterior borró el índice de paquetes.
RUN apt-get update && \
    rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y && \
    rm -rf /var/lib/apt/lists/*

# xarm_gazebo SIEMPRE se compila aquí, tenga o no la máquina GPU: compilar no
# necesita aceleración gráfica, solo CORRER Gazebo con render la necesita.
# xarm_moveit_config depende de xarm_gazebo, así que saltarlo rompe el build.
RUN /bin/bash -c "source /opt/ros/${ROS_DISTRO}/setup.bash && colcon build"

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
