#!/bin/bash
# コンテナ内で実行: bash /workspace/setup_ollama.sh
# Ollama を入れて起動し、モデルを取得する。
# モデルはコンテナ内（~/.ollama）に保存する。/workspace（Windows のフォルダ）に大きなファイルを
# 書き込むと input/output error になるため。コンテナを作り直した場合はもう一度ダウンロードが必要。
MODEL=${1:-qwen2.5:1.5b}
mkdir -p /workspace/log
if ! command -v ollama >/dev/null; then
  echo "== Ollama をインストールします（パスワードを聞かれたら入力）"
  curl -fsSL https://ollama.com/install.sh | sh
fi
# 起動中のサーバーがあれば止めてから、コンテナ内保存の設定で起動し直す
pkill -x ollama 2>/dev/null && sleep 1
echo "== Ollama サーバーを起動します（ログ: /workspace/log/ollama.log）"
nohup ollama serve > /workspace/log/ollama.log 2>&1 &
sleep 3
echo "== モデル $MODEL を取得します"
ollama pull "$MODEL" || exit 1
echo "== 動作確認"
ollama run "$MODEL" "「ついてきて」を英語で一言で"
