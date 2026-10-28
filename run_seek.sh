#!/bin/bash
# 使い方: bash /workspace/run_seek.sh [目標の物体名] [モード]
#   例: bash /workspace/run_seek.sh person follow     (ついていく)
#       bash /workspace/run_seek.sh person approach   (近づいて止まる)
source /opt/ros/humble/setup.bash
source /workspace/install/setup.bash
cd /workspace
ros2 launch pai_seek seek.launch.py target:=${1:-person} mode:=${2:-follow}
