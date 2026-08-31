FROM osrf/ros:jazzy-desktop

ARG WITH_GAZEBO=false

ENV DEBIAN_FRONTEND=noninteractive
ENV ROS_DISTRO=jazzy

RUN apt-get update && apt-get install -y \
    python3-colcon-common-extensions \
    python3-rosdep \
    git \
    ros-${ROS_DISTRO}-moveit \
    && rm -rf /var/lib/apt/lists/*

RUN if [ "$WITH_GAZEBO" = "true" ]; then \
      apt-get update && apt-get install -y \
        ros-${ROS_DISTRO}-ros-gz-sim \
        ros-${ROS_DISTRO}-ros-gz-bridge \
        ros-${ROS_DISTRO}-gz-ros2-control \
      && rm -rf /var/lib/apt/lists/* ; \
    fi

RUN mkdir -p /root/xarm_ws/src
WORKDIR /root/xarm_ws

COPY src/xarm_ros2 /root/xarm_ws/src/xarm_ros2

RUN rosdep update && \
    rosdep install --from-paths src --ignore-src -r -y

RUN /bin/bash -c "source /opt/ros/${ROS_DISTRO}/setup.bash && \
    if [ \"$WITH_GAZEBO\" = \"true\" ]; then \
      colcon build ; \
    else \
      colcon build --packages-skip xarm_gazebo ; \
    fi"

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
