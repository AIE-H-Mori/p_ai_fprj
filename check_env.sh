#!/bin/bash
# コンテナ内で実行: bash /workspace/check_env.sh
source /opt/ros/humble/setup.bash
echo "== ROS_DISTRO: $ROS_DISTRO"
echo "== turtlebot3 packages:"; ros2 pkg list | grep -E "^turtlebot3" || echo "  (none)"
echo "== gazebo_ros:"; ros2 pkg list | grep -E "^gazebo_ros$" || echo "  (none)"
echo "== python:"; python3 --version
python3 -c "import cv_bridge; print('cv_bridge OK')" 2>&1
python3 -c "import ultralytics; print('ultralytics', ultralytics.__version__)" 2>&1 | tail -1
python3 -c "import torch; print('torch', torch.__version__)" 2>&1 | tail -1
echo "== disk:"; df -h / | tail -1
