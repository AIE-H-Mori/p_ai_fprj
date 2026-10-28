#!/bin/bash
# ロボット目線の動画を録画する（start_demo.sh で起動した後、別のターミナルで）
#   bash /workspace/record.sh    → Ctrl+C で終了・保存（/workspace/videos/）
source /opt/ros/humble/setup.bash
source /workspace/install/setup.bash
ros2 run pai_seek recorder
