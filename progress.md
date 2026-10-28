# PAI応用1 最終課題 進捗メモ

締切: 2026-11-02(月) 10:00 / 提出開始 10-19。提出物: 動画1〜3分(YouTube)、GitHub public、レポートPDF。

## テーマ
言葉で指示して物体を探す TurtleBot3（A: YOLOで探して近づく → B: LLMで指示文から目標を決める）

## 環境
- Docker: airobotbook/ros2-desktop-ai-robot-book-humble（ROS 2 Humble + Gazebo Classic）、コンテナ名 pai_final、http://localhost:6081
- コード: G:\Study\PAI_final_project を /workspace にマウント（S:のファイルサーバはDockerから見えないため不可）
- GPUはRadeon → YOLOはCPU推論。ultralytics 8.3.74 はイメージに同梱。pipで numpy 等を更新しない（cv_bridge破損防止）

## 構成（src/pai_seek）
- detector: /camera/image_raw/compressed を受信（非圧縮は取りこぼして灰色になるため）→ yolo11n(CPU, 5Hz) → /detections(JSON), /detector/image/compressed
- controller: SEARCH(最後に見えた方向へ回転) → APPROACH(カメラで向き補正) → CLOSE(見失った時1.5m以内に物体があればLiDARで寄る) → ARRIVED(前方0.6m)。/target で目標変更可
- 起動: bash /workspace/run_seek.sh person

## 状況（2026-10-10）
- A 完成: empty_world + person_standing で到達確認（arrived at person 0.58 m）
- 次: Aの動画を撮っておく → B（instruction ノード、LLM選定: API か Ollama）→ YOLO-World で「赤い箱」等

## レポートに書ける工夫点
- 非圧縮画像の取りこぼし → 圧縮画像で受信
- 近距離で足しか映らず検出が途切れる → LiDARに切替（センサーの使い分け）、ばたつき防止のヒステリシス
- 見失った方向へ回る探索