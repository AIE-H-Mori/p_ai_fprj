"""指示文（日本語）を LLM（Ollama）で解釈し、controller の /mode と /target に変換するノード。

subscribe: /instruction (String)   例: "人についてきて" "そこで待って" "椅子のところに行って"
publish:   /mode (String: follow / approach / stop)
           /target (String: YOLO のクラス名。例 person, chair)
           /robot_reply (String: ロボットの返事)

LLM が使えない・おかしな答えを返したときは、キーワード照合で代わりに解釈する（フォールバック）。
"""
import json
import time
import urllib.request

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

MODES = ['follow', 'approach', 'stop']

# 日本語 → YOLO(COCO) クラス名。LLM へのヒントとフォールバックの両方に使う
TARGETS = {
    'person': ['人', 'ひと', '私', 'わたし', '僕', 'ぼく', '俺', 'おれ', 'あなた', '彼', '彼女', 'ご主人'],
    'chair': ['椅子', 'いす', 'イス', 'チェア'],
    'bottle': ['ボトル', 'ペットボトル', 'びん', '瓶'],
    'cup': ['カップ', 'コップ', 'マグ'],
    'potted plant': ['植木', '観葉植物', '鉢', '植物'],
    'couch': ['ソファ', 'ソファー'],
    'tv': ['テレビ', 'TV'],
    'dog': ['犬', 'いぬ', 'イヌ'],
    'cat': ['猫', 'ねこ', 'ネコ'],
    'fire hydrant': ['消火栓'],
    'stop sign': ['標識', 'ストップサイン'],
    'car': ['車', 'くるま', 'クルマ', '自動車'],
}
MODE_WORDS = {
    'stop': ['止ま', 'とま', '待', 'まって', 'ストップ', 'stop', 'じっと', 'そこにい'],
    'follow': ['ついて', '付いて', 'ついてきて', '追いかけ', '追って', 'フォロー'],
    'approach': ['行って', 'いって', '近づ', 'まで', '向かって', 'のところ', 'へ行',
                 '来て', 'きて', 'おいで', 'こっち'],
}

SYSTEM_PROMPT = """あなたは家庭用の移動ロボットの指示解釈係です。
ユーザーの日本語の指示を読み、ロボットの動作を JSON で答えてください。

mode は次のどれか1つ:
- "follow"   : 対象についていく（例「ついてきて」「追いかけて」）
- "approach" : 対象のところへ行って止まる（例「〇〇のところへ行って」「私のところへ来て」「こっちに来て」）
- "stop"     : その場で待つ（例「止まって」「待って」）
「来て」「おいで」は話し手（person）のところへ来る approach です。stop ではありません。

例:
- 私のところへきて → mode=approach, target=person
- こっちに来て → mode=approach, target=person
- 私についてきて → mode=follow, target=person
- そこで待っていて → mode=stop, target=none
- 車のところに行って → mode=approach, target=car

target は次の英語のどれか1つ（stop のときや対象がないときは "none"）:
{targets}
日本語との対応: {hints}
「私」「僕」など話し手自身は person です。

reply はロボットの短い返事（日本語、20文字以内）。
"""


class Instruction(Node):
    def __init__(self):
        super().__init__('instruction')
        self.declare_parameter('ollama_url', 'http://localhost:11434')
        self.declare_parameter('model', 'qwen2.5:1.5b')
        self.declare_parameter('timeout', 30.0)
        self.declare_parameter('use_llm', True)

        hints = ', '.join(f'{v[0]}={k}' for k, v in TARGETS.items())
        self.system = SYSTEM_PROMPT.format(targets=', '.join(TARGETS), hints=hints)
        self.schema = {
            'type': 'object',
            'properties': {
                'mode': {'type': 'string', 'enum': MODES},
                'target': {'type': 'string', 'enum': list(TARGETS) + ['none']},
                'reply': {'type': 'string'},
            },
            'required': ['mode', 'target', 'reply'],
        }
        self.create_subscription(String, '/instruction', self.on_instruction, 10)
        self.pub_mode = self.create_publisher(String, '/mode', 10)
        self.pub_target = self.create_publisher(String, '/target', 10)
        self.pub_reply = self.create_publisher(String, '/robot_reply', 10)
        self.get_logger().info(f'instruction ready (model = {self.get_parameter("model").value})')

    # ---- LLM ----
    def ask_llm(self, text):
        body = {
            'model': self.get_parameter('model').value,
            'messages': [{'role': 'system', 'content': self.system},
                         {'role': 'user', 'content': text}],
            'format': self.schema,          # JSON の形を指定（Ollama の structured outputs）
            'stream': False,
            'options': {'temperature': 0},
        }
        req = urllib.request.Request(
            self.get_parameter('ollama_url').value + '/api/chat',
            data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=self.get_parameter('timeout').value) as r:
            content = json.loads(r.read())['message']['content']
        ans = json.loads(content)
        if isinstance(ans, dict) and ans.get('target') == 'none':
            ans['target'] = None
        return ans

    # ---- フォールバック（キーワード照合）----
    @staticmethod
    def by_keywords(text):
        mode = next((m for m, ws in MODE_WORDS.items() if any(w in text for w in ws)), None)
        target = next((t for t, ws in TARGETS.items() if any(w in text for w in ws)), None)
        if mode is None:
            return None
        return {'mode': mode, 'target': target, 'reply': {
            'follow': 'ついていきます', 'approach': '向かいます', 'stop': '待ちます'}[mode]}

    @staticmethod
    def valid(ans):
        return isinstance(ans, dict) and ans.get('mode') in MODES and \
            (ans.get('target') in TARGETS or ans.get('target') is None)

    # ---- main ----
    def on_instruction(self, msg):
        text = msg.data.strip()
        if not text:
            return
        self.get_logger().info(f'指示: {text}')
        self.say('考えています…')   # 受け取ったことをすぐ返す（LLM は数秒かかる）
        ans, source = None, 'LLM'
        if self.get_parameter('use_llm').value:
            t0 = time.time()
            try:
                ans = self.ask_llm(text)
                self.get_logger().info(f'LLM ({time.time() - t0:.1f} s): {ans}')
            except Exception as e:  # 接続できない・時間切れ・JSON でない など
                self.get_logger().warn(f'LLM error: {e}')
        if not self.valid(ans):
            ans, source = self.by_keywords(text), 'keyword'
        else:
            # 食い違いチェック：LLM が stop と答えたのに、指示文に「待つ・止まる」の言葉がなく
            # 「来て」「ついて」など動く言葉があるときは、キーワード照合の結果を優先する
            kw = self.by_keywords(text)
            if ans['mode'] == 'stop' and kw and kw['mode'] != 'stop':
                self.get_logger().warn(f'LLM の答え（stop）が指示文と食い違うため、キーワード照合を使います: {kw}')
                ans, source = kw, 'keyword(LLMと食い違い)'
        if ans is None:
            self.say('すみません、わかりませんでした')
            return
        if ans['mode'] in ('follow', 'approach') and ans['target'] is None:
            ans['target'] = 'person'   # 対象が言われていなければ話し手（人）とみなす
        self.get_logger().info(f'[{source}] mode={ans["mode"]} target={ans["target"]}')
        if ans['target'] and ans['mode'] != 'stop':
            self.pub_target.publish(String(data=ans['target']))
        self.pub_mode.publish(String(data=ans['mode']))
        self.say(ans.get('reply') or '了解しました')

    def say(self, text):
        self.get_logger().info(f'ロボット: {text}')
        self.pub_reply.publish(String(data=text))


def main():
    rclpy.init()
    node = Instruction()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.try_shutdown()
