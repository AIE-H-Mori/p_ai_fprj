#!/bin/bash
# Gazebo に、YOLO（COCO）で見分けられそうな物体を置く（Gazebo 起動後に実行）
#   bash /workspace/spawn_objects.sh          → 置く
#   bash /workspace/spawn_objects.sh remove   → 消す
# ロボットは原点で +X 方向（前）を向いている。人は前方 3.5m（start_demo.sh が置く）
source /opt/ros/humble/setup.bash
# 名前  Gazeboモデル  x  y  向き(rad)   ※YOLOでのクラス名はコメント
OBJECTS=(
  "hydrant    fire_hydrant  0.0   3.0  0.0"    # fire hydrant（消火栓）: 左
  "stopsign   stop_sign     0.0  -3.0  1.57"   # stop sign（標識）: 右
  "car        hatchback    -4.5   0.0  1.57"   # car（車）: 後ろ
)
for o in "${OBJECTS[@]}"; do
  read name model x y yaw <<< "$o"
  if [ "$1" = "remove" ]; then
    ros2 service call /delete_entity gazebo_msgs/srv/DeleteEntity "{name: '$name'}" >/dev/null && echo "removed $name"
  else
    ros2 run gazebo_ros spawn_entity.py -database "$model" -entity "$name" -x "$x" -y "$y" -Y "$yaw" \
      >/dev/null 2>&1 && echo "OK   $name ($model)" || echo "NG   $name ($model) ※モデルが見つからないか、すでに置いてある"
  fi
done
