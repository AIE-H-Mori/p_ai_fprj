#!/bin/bash
# 指示を入力する（PowerShell から docker exec で入ったシェルで実行）
#   bash /workspace/talk.sh
export LANG=C.UTF-8
source /opt/ros/humble/setup.bash
source /workspace/install/setup.bash
ros2 run pai_seek talk
