#!/bin/bash
# デモ一式をまとめて起動する（コンテナのデスクトップ画面のターミナルで実行）
#   bash /workspace/start_demo.sh            → Ollama・Gazebo・人・検出/制御/指示ノードを起動（待機状態）
# 終了は Ctrl+C（Gazebo も一緒に止まる）。指示は PowerShell 側から talk で入力する。
source /opt/ros/humble/setup.bash
cd /workspace
mkdir -p log
export TURTLEBOT3_MODEL=waffle

# 1. Ollama（止まっていれば起動）
if ! curl -s http://localhost:11434 >/dev/null; then
  echo "== Ollama を起動します"
  nohup ollama serve > /workspace/log/ollama.log 2>&1 &
  sleep 3
fi

# 2. ビルド
colcon build --symlink-install || exit 1
source install/setup.bash

# 3. Gazebo（ログは log/gazebo.log）
echo "== Gazebo を起動します"
ros2 launch turtlebot3_gazebo empty_world.launch.py > log/gazebo.log 2>&1 &
GZ=$!
trap "kill $GZ 2>/dev/null; pkill -f gzserver; pkill -f gzclient" EXIT

# 4. Gazebo の準備を待って人を置く
for i in $(seq 1 60); do
  ros2 service list 2>/dev/null | grep -q /spawn_entity && break
  sleep 1
done
ros2 run gazebo_ros spawn_entity.py -database person_standing -entity person -x 3.5 -y 0.0 \
  > log/spawn.log 2>&1 || echo "（人はすでに置いてあるか、置けませんでした。log/spawn.log を確認）"

# 5. 検出・制御・指示ノード（待機状態で開始）
echo "== 準備完了。PowerShell から talk で指示してください"
ros2 launch pai_seek seek.launch.py target:=person mode:=stop
