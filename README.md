# PAI 最終課題：言葉で指示できる、ついてくるお手伝いロボット（TurtleBot3）

YOLO（物体検出）で目標を見つけ、LiDAR と組み合わせて「近づいて止まる」「ついていく」を行う TurtleBot3 のシミュレーションです。
次の段階（B）で、LLM が指示文（「ついてきて」「待って」など）をロボットの動作に変換します。

| 段階 | 内容 | 状況 |
| --- | --- | --- |
| A | YOLO で目標を探して近づく・止まる | 完成 |
| A+ | 人との距離を保ってついていく（follow） | 完成 |
| B | LLM（Ollama + Qwen2.5 1.5B）で指示文から目標とモードを決める | 完成 |
| C | 人以外の物体も置き、言葉で目標を切り替える | 作業中 |

---

## クイックスタート（毎回の手順）

最初の1回だけ必要な準備（コンテナ作成、Ollama のインストール）は 2 章と 4.5 章を参照。2回目以降は次の5ステップで動く。

**① コンテナを起動する**（Docker Desktop を起動してから PowerShell で）

```powershell
docker start pai_final
```

ブラウザで http://localhost:6081 を開く。

**② まとめて起動する**（①のブラウザ画面の中のターミナルで）

```bash
bash /workspace/start_demo.sh
```

Gazebo が開き、人が置かれ、「準備完了」と出るまで待つ（1〜2分）。少し遅れて、ロボット目線の映像（YOLO の枠付き）のウィンドウも開く。映像が出ないときは、ウィンドウ左上のプルダウンで `/detector/image/compressed` を選ぶ（一度選べば次回から覚えている）。

**③ 指示用のターミナルを開く**（①のブラウザ画面の中で、もう1つターミナルを開く）

```bash
bash /workspace/talk.sh
```

ブラウザ画面の中で日本語が入力できない場合は、代わりに Windows の PowerShell からコンテナに入って同じコマンドを実行する。

```powershell
chcp 65001
docker exec -it -u ubuntu pai_final bash
```

**④ 指示する**：「指示>」に入力して Enter

| 指示の例 | ロボットの動き |
| --- | --- |
| 人についてきて | 人を探し、約1mの距離を保ってついていく（人は Gazebo の十字矢印ツール＝キー T でドラッグして動かせる） |
| わたしのところにきて | 人の前まで行って止まる |
| そこで待っていて | その場で止まる |

指示を受け取るとすぐ「考えています…」と返事が出て、数秒後に LLM の返事が出る。

**⑤ 終わる**：②と③のターミナルで Ctrl+C。保存は 8 章（Git）。

| 困ったとき | 確認すること |
| --- | --- |
| 「考えています…」も出ない | ②が動いているか。`ros2 node list` に `/instruction` があるか |
| 「考えています…」の後が来ない | Ollama が動いているか（`bash /workspace/setup_ollama.sh` で起動し直す） |
| 文字化け・「読み取れない文字」 | ③で `chcp 65001` をしたか。Windows Terminal を使うと安定する |

---

## 1. 前提

- Windows + Docker Desktop
- Docker イメージ：`airobotbook/ros2-desktop-ai-robot-book-humble`（第4・5回の演習と同じ。ROS 2 Humble + Gazebo）
- このフォルダは**ローカルドライブ**に置く（例 `G:\Study\PAI_final_project`）
  - ファイルサーバやネットワークドライブ（S: など）は Docker から見えないため不可
- GPU は不要（YOLO は CPU で推論。Radeon でも可）
- YOLO（ultralytics）はイメージに入っているので追加インストール不要
  - **pip で numpy などを更新しない**（cv_bridge が壊れることがある）

## 2. コンテナを作る（最初の1回だけ）

PowerShell で実行します。

```powershell
docker run -d --name pai_final -p 6081:80 --shm-size=1g `
  -v "G:\Study\PAI_final_project:/workspace" `
  airobotbook/ros2-desktop-ai-robot-book-humble:latest
```

- 2回目以降は `docker start pai_final` だけでよい
- ブラウザで http://localhost:6081 を開くとデスクトップ画面が出る。以下のコマンドはその中のターミナルで実行する
- 環境チェック：`bash /workspace/check_env.sh`（turtlebot3、gazebo_ros、ultralytics が表示されれば OK）

## 3. ビルド（コードを変えたら毎回）

```bash
source /opt/ros/humble/setup.bash
cd /workspace && colcon build --symlink-install
```

## 4. 動かす

**まとめて起動する場合**（おすすめ）：コンテナのデスクトップ画面のターミナルで `bash /workspace/start_demo.sh`。Ollama・Gazebo・人・各ノードを順に起動し、待機状態になる。指示は 4.5 の talk で行う。

**1つずつ起動する場合**（ターミナルを3つ使う）

**ターミナル1：Gazebo を起動**

```bash
source /opt/ros/humble/setup.bash
export TURTLEBOT3_MODEL=waffle
ros2 launch turtlebot3_gazebo empty_world.launch.py
```

**ターミナル2：人を置く**

```bash
source /opt/ros/humble/setup.bash
ros2 run gazebo_ros spawn_entity.py -database person_standing -entity person -x 3.5 -y 0.0
```

- 正面 3.5m に置く。近すぎる（2m など）と足しか映らず検出されない
- 置き直すときは、先に消す：`ros2 service call /delete_entity gazebo_msgs/srv/DeleteEntity "{name: 'person'}"`
- 後ろに置くと「回って探す」動作を確認できる：`-x -3.0 -y 1.5`
- `Entity [person] already exists` は「もう置いてある」という意味で、エラーではない
- **マウスで人を動かす**：Gazebo 上部ツールバーの十字矢印（Translate モード、キー T）→ 人をクリック → 赤(X)・緑(Y)の矢印をドラッグ。戻すときは矢印アイコン（Select モード、Esc）

**ターミナル3：検出と制御を起動**

```bash
bash /workspace/run_seek.sh person follow     # ついていく
bash /workspace/run_seek.sh person approach   # 近づいて止まる
```

- 終了は Ctrl+C
- 実行中にモードや目標を変える（別のターミナルで）：

```bash
source /opt/ros/humble/setup.bash
ros2 topic pub --once /mode std_msgs/String "data: stop"      # 待機（follow / approach / stop）
ros2 topic pub --once /target std_msgs/String "data: chair"   # 目標を変える
```

## 4.5 言葉で指示する（B）

**Ollama の準備**（コンテナを起動するたびに1回。初回はインストールとモデル約1GBのダウンロードも行う）

```bash
bash /workspace/setup_ollama.sh
```

- モデルはコンテナ内（`~/.ollama`）に保存する。/workspace（Windows のフォルダ）に保存すると input/output error になる
- G: ドライブの空きが少ないとビルドも失敗する。数GB以上空けておく

**起動**：`bash /workspace/run_seek.sh person stop`（instruction ノードも一緒に起動。最初は待機）

**指示を入力**：コンテナのデスクトップ画面のターミナルで実行する（日本語が入力できない環境では、Windows の PowerShell から入る）

```powershell
docker exec -it -u ubuntu pai_final bash
```

```bash
export LANG=C.UTF-8
source /opt/ros/humble/setup.bash && source /workspace/install/setup.bash
ros2 run pai_seek talk
```

「指示>」に「人についてきて」「そこで待って」などを入力する。LLM が使えないときはキーワード照合で解釈する。

## 5. 様子を確認する

| 見たいもの | コマンド |
| --- | --- |
| 検出結果 | `ros2 topic echo /detections` |
| 制御の状態・距離 | `ros2 topic echo /seek/state` |
| 枠付きの映像 | `ros2 run rqt_image_view rqt_image_view` → `/detector/image/compressed` |
| カメラ映像 | 同上 → `/camera/image_raw/compressed`（`image_raw` は灰色になることがある） |

いずれも先に `source /opt/ros/humble/setup.bash` を実行する。

## 6. 仕組み

```
カメラ(圧縮画像) ──▶ [detector] YOLO11n (CPU, 5Hz) ──▶ /detections（物体名・横位置・枠の高さ）
                                                       │
                     /target, /mode（B で LLM から） ──▶ [controller] ──▶ /cmd_vel
                                                       ▲
                                         LiDAR /scan（正面の距離・一番近い物体の角度）
```

controller の状態

| 状態 | 動き | 次の状態へ |
| --- | --- | --- |
| SEARCH | 最後に見えた方向へその場で回る | 目標が見えたら APPROACH |
| APPROACH | カメラの横位置で向きを直しながら前進 | follow：LiDAR で 1.5m 以内なら FOLLOW / approach：前方 0.6m で ARRIVED / 見失い：近くに物体があれば CLOSE、なければ SEARCH |
| CLOSE | 足しか映らず検出が途切れたとき、LiDAR で一番近い物体に寄る | 1 秒間近くに何もなければ SEARCH |
| FOLLOW | 距離 1.0m を保つ（離れたら追う・近すぎたら下がる） | カメラと LiDAR の両方で見失ったら SEARCH |
| ARRIVED / WAIT | 停止 | /mode や /target で再開 |

## 7. つまずいたところと対処

| 症状 | 原因 | 対処 |
| --- | --- | --- |
| `check_env.sh` が見つからない、/workspace が空 | フォルダがファイルサーバ（S:）にあり Docker から見えない | ローカルドライブにコピーしてコンテナを作り直す |
| rqt で `image_raw` が灰色のまま | 非圧縮画像は大きく、通信で取りこぼす | 圧縮画像（`/compressed`）を使う。detector も圧縮画像で受信 |
| 足しか映らず検出されない | 人が近すぎる（カメラが低い位置にある） | 人を 3.5m 以上離して置く |
| `Package 'pai_seek' not found` | 新しいターミナルでビルド結果を読み込んでいない | `run_seek.sh` を使う（読み込みも行う） |
| 近づくとぐるぐる回る | 近距離で YOLO が見失い探索に戻っていた | 近距離は LiDAR に切り替える CLOSE 状態を追加 |
| talk で入力しても反応しない | コンテナ再起動後、run_seek.sh（instruction ノード）を起動し直していなかった | `ros2 node list` で確認。start_demo.sh でまとめて起動する |
| Ollama のモデル取得で input/output error、ビルドも失敗 | G: ドライブの空きが 0。モデルを /workspace に保存しようとしていた | 空きを作り、モデルはコンテナ内に保存 |
| CLOSE と SEARCH が高速に入れ替わる | 枠の大きさで「近い」と判定したが、実際は遠かった | 「カメラで見失った＋LiDAR で 1.5m 以内」を条件にし、抜けるのは 1 秒続いたときだけにした |
| `/seek/state` が `front=inf` | LiDAR の届く距離（約 3.5m）より遠い | 故障ではない。近づけば値が出る |

## 8. Git で保存する

```bash
cd /workspace
git config --global --add safe.directory /workspace   # 初回だけ
git add . && git commit -m "変更内容"
```

`build/` `install/` `log/`、YOLO の重み（`*.pt`）、録画ファイル（`videos/`）などは `.gitignore` で除外済み。

### コミット済みのファイルを公開対象から外す

`.gitignore` に書いても、**すでにコミットしたファイルは除外されない**。手元のファイルは残したまま Git の管理からだけ外すには `git rm --cached` を使う。

```bash
cd /workspace
echo 'ファイル名' >> .gitignore          # まだ書いていなければ .gitignore に追加
git rm --cached ファイル名               # Git の管理から外す（手元のファイルは消えない）
git add .gitignore
git commit -m "ファイル名 を公開対象から外す"
git ls-files                             # 公開されるファイルの一覧で確認
```

- フォルダごと外すときは `git rm -r --cached フォルダ名`
- `--cached` を付け忘れると、手元のファイルも削除されるので注意
- 過去のコミットの中身には残る。パスワードなど見られて困るものをコミットしてしまった場合は、履歴ごと消す必要がある（公開前なら、リポジトリを作り直すのが簡単）

### コミットの作者情報（名前・メールアドレス）を直す

コミットには作者の名前とメールアドレスが記録され、GitHub で公開すると誰でも見られる。個人のメールアドレスを出したくないときは、GitHub の Settings → Emails に表示される `…@users.noreply.github.com` を使う。

```bash
cd /workspace
git config user.name "GitHub のユーザー名"
git config user.email "ID+ユーザー名@users.noreply.github.com"
git log --format='%h %an <%ae> %s'       # 今の作者情報を確認
```

すでにあるコミットを直すとき（push する前に行う）：

```bash
# 最新の1つだけ
git commit --amend --reset-author --no-edit
# 最初のコミットから全部
git rebase -r --root --exec "git commit --amend --reset-author --no-edit"
```

最後にもう一度 `git log --format='%h %an <%ae> %s'` で確認する。

## ライセンス

GNU Affero General Public License v3.0（AGPL-3.0）。全文は [LICENSE](LICENSE) を参照。

物体検出に使っている Ultralytics YOLO が AGPL-3.0 のため、このリポジトリのコードも同じライセンスで公開しています。そのほかに使っているもののライセンスは次のとおり。

| 名前 | ライセンス |
| --- | --- |
| ROS 2 Humble / Gazebo Classic / TurtleBot3 | Apache-2.0 |
| Ultralytics YOLO11 | AGPL-3.0 |
| Ollama | MIT |
| Qwen2.5 1.5B（モデルの重み） | Apache-2.0 |
