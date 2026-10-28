"""ターミナルで指示を入力して /instruction に送り、ロボットの返事（/robot_reply）を表示する。

使い方: ros2 run pai_seek talk   → 「指示> 」に日本語で入力して Enter（終了は Ctrl+C）
"""
import readline  # noqa: F401  入力行の編集（Backspace で日本語1文字ずつ消す）を正しく扱う
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class Talk(Node):
    def __init__(self):
        super().__init__('talk')
        self.pub = self.create_publisher(String, '/instruction', 10)
        self.create_subscription(String, '/robot_reply', self.on_reply, 10)

    def on_reply(self, msg):
        print(f'\nロボット> {msg.data}\n指示> ', end='', flush=True)


def main():
    rclpy.init()
    node = Talk()
    threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()
    try:
        while rclpy.ok():
            raw = input('指示> ')
            # 端末から壊れた文字（不完全な UTF-8）が来ても落ちないよう、読めない部分は捨てる
            text = raw.encode('utf-8', 'surrogateescape').decode('utf-8', 'ignore').strip()
            if raw and text != raw.strip():
                print('（読み取れない文字があったので除きました）')
            if text:
                node.pub.publish(String(data=text))
    except (KeyboardInterrupt, EOFError):
        pass
    node.destroy_node()
    rclpy.try_shutdown()
