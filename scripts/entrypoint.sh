#!/bin/bash
set -e

source /opt/ros/jazzy/setup.bash
source /root/xarm_ws/install/setup.bash

exec "$@"
