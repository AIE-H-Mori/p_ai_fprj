"""ロボットのカメラ映像に、YOLO の枠・状態・指示と返事を重ねて mp4 に録画するノード（動画用）。

使い方: ros2 run pai_seek recorder   → Ctrl+C で録画終了・保存
保存先: /workspace/videos/robot_view_日付_時刻.mp4

カメラ映像（毎秒約30枚）に、最新の検出結果（毎秒5回）を重ねて、fps 枚/秒で書き出す。
"""
import json
import os
import time

import cv2
import numpy as np
import rclpy
from PIL import Image, ImageDraw, ImageFont
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

FONT_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',
    '/usr/share/fonts/truetype/takao-gothic/TakaoPGothic.ttf',
    '/usr/share/fonts/truetype/vlgothic/VL-Gothic-Regular.ttf',
]


def load_font(size):
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size), True
    return ImageFont.load_default(), False   # 日本語フォントがない場合（日本語は表示されない）


class Recorder(Node):
    def __init__(self):
        super().__init__('recorder')
        self.declare_parameter('out_dir', '/workspace/videos')
        self.declare_parameter('fps', 15.0)
        self.declare_parameter('width', 960)       # 書き出す動画の横幅（高さは比率を保つ）
        self.declare_parameter('target', 'person')

        self.frame = None
        self.dets, self.det_time = [], 0.0
        self.state = ''
        self.target = self.get_parameter('target').value
        self.instruction = ''
        self.reply = ''
        self.writer = None
        self.n = 0
        self.font, self.jp_ok = load_font(22)
        self.font_small, _ = load_font(18)
        if not self.jp_ok:
            self.get_logger().warn('日本語フォントが見つかりません。指示と返事の文字は表示されません'
                                   '（sudo apt install -y fonts-noto-cjk で入ります）')

        os.makedirs(self.get_parameter('out_dir').value, exist_ok=True)
        self.path = os.path.join(self.get_parameter('out_dir').value,
                                 time.strftime('robot_view_%Y%m%d_%H%M%S.mp4'))

        self.create_subscription(CompressedImage, '/camera/image_raw/compressed',
                                 self.on_image, qos_profile_sensor_data)
        self.create_subscription(String, '/detections', self.on_det, 10)
        self.create_subscription(String, '/seek/state', self.on_state, 10)
        self.create_subscription(String, '/target', self.on_target, 10)
        self.create_subscription(String, '/instruction', self.on_instruction, 10)
        self.create_subscription(String, '/robot_reply', self.on_reply, 10)
        self.create_timer(1.0 / self.get_parameter('fps').value, self.tick)
        self.get_logger().info(f'録画を始めます → {self.path}（Ctrl+C で終了）')

    # ---- callbacks ----
    def on_image(self, msg):
        self.frame = msg

    def on_det(self, msg):
        self.dets, self.det_time = json.loads(msg.data), time.time()

    def on_state(self, msg):
        self.state = msg.data

    def on_target(self, msg):
        self.target = msg.data.strip()

    def on_instruction(self, msg):
        self.instruction, self.reply = msg.data.strip(), ''

    def on_reply(self, msg):
        self.reply = msg.data.strip()

    # ---- 描画と書き出し ----
    def draw(self, img):
        h, w = img.shape[:2]
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        d = ImageDraw.Draw(pil, 'RGBA')
        # YOLO の枠（0.5 秒以上古い結果は描かない）
        if time.time() - self.det_time < 0.5:
            for det in self.dets:
                if 'box' not in det:
                    continue
                x1, y1, x2, y2 = det['box']
                is_target = det['cls'] == self.target
                color = (255, 200, 0, 255) if is_target else (0, 200, 255, 255)
                d.rectangle([x1 * w, y1 * h, x2 * w, y2 * h], outline=color, width=4 if is_target else 2)
                d.text((x1 * w + 4, max(0, y1 * h - 24)), f"{det['cls']} {det['conf']:.2f}",
                       fill=color, font=self.font_small)
        # 上：状態（英数字のみ）
        state = self.state.split(' front=')[0] if self.state else 'waiting...'
        d.rectangle([0, 0, w, 34], fill=(0, 0, 0, 150))
        d.text((10, 6), state, fill=(255, 255, 255, 255), font=self.font_small)
        # 下：指示と返事
        if self.jp_ok and (self.instruction or self.reply):
            d.rectangle([0, h - 70, w, h], fill=(0, 0, 0, 150))
            d.text((10, h - 64), f'指示：{self.instruction}', fill=(255, 255, 255, 255), font=self.font)
            d.text((10, h - 34), f'ロボット：{self.reply}', fill=(255, 220, 120, 255), font=self.font)
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    def tick(self):
        if self.frame is None:
            return
        img = cv2.imdecode(np.frombuffer(self.frame.data, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return
        W = int(self.get_parameter('width').value)
        img = cv2.resize(img, (W, int(img.shape[0] * W / img.shape[1])))
        img = self.draw(img)
        if self.writer is None:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.writer = cv2.VideoWriter(self.path, fourcc, self.get_parameter('fps').value,
                                          (img.shape[1], img.shape[0]))
        self.writer.write(img)
        self.n += 1

    def close(self):
        if self.writer is not None:
            self.writer.release()
            sec = self.n / self.get_parameter('fps').value
            print(f'保存しました: {self.path}（{sec:.0f} 秒）', flush=True)
        else:
            print('カメラ画像が届かなかったので、何も保存していません', flush=True)


def main():
    rclpy.init()
    node = Recorder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.close()      # これを呼ばないと mp4 が壊れる
    node.destroy_node()
    rclpy.try_shutdown()
