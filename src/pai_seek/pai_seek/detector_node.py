"""カメラ画像を YOLO で推論し、検出結果を JSON 文字列で publish するノード。

publish:
  /detections      std_msgs/String  例: [{"cls":"person","conf":0.83,"cx":0.12,"h":0.45}, ...]
                   cx = 画面中心からの横ずれ（-1 左端 〜 +1 右端）、h = 枠の高さ / 画像の高さ
  /detector/image/compressed  sensor_msgs/CompressedImage  枠を描いた画像（動画撮影用）

カメラは圧縮画像（/camera/image_raw/compressed）で受け取る。
非圧縮の画像はサイズが大きく、DDS で取りこぼして灰色になることがあるため。
"""
import json

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String
from ultralytics import YOLO


class Detector(Node):
    def __init__(self):
        super().__init__('detector')
        self.declare_parameter('model', 'yolo11n.pt')
        self.declare_parameter('image_topic', '/camera/image_raw/compressed')
        self.declare_parameter('rate_hz', 5.0)      # CPU 推論なので間引く
        self.declare_parameter('conf', 0.4)
        self.declare_parameter('imgsz', 416)

        self.model = YOLO(self.get_parameter('model').value)
        self.conf = self.get_parameter('conf').value
        self.imgsz = self.get_parameter('imgsz').value
        self.latest = None

        self.create_subscription(CompressedImage, self.get_parameter('image_topic').value,
                                 self.on_image, qos_profile_sensor_data)
        self.pub_det = self.create_publisher(String, '/detections', 10)
        self.pub_img = self.create_publisher(CompressedImage, '/detector/image/compressed', 10)
        self.create_timer(1.0 / self.get_parameter('rate_hz').value, self.tick)
        self.get_logger().info('detector ready')

    def on_image(self, msg):
        self.latest = msg  # 最新フレームだけ保持し、推論はタイマーで行う

    def tick(self):
        if self.latest is None:
            return
        frame = cv2.imdecode(np.frombuffer(self.latest.data, np.uint8), cv2.IMREAD_COLOR)
        self.latest = None
        if frame is None:
            return
        h, w = frame.shape[:2]
        res = self.model.predict(frame, conf=self.conf, imgsz=self.imgsz,
                                 device='cpu', verbose=False)[0]
        dets = []
        for box in res.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            dets.append({
                'cls': res.names[int(box.cls)],
                'conf': round(float(box.conf), 3),
                'cx': round(((x1 + x2) / 2 - w / 2) / (w / 2), 3),
                'h': round((y2 - y1) / h, 3),
            })
        self.pub_det.publish(String(data=json.dumps(dets)))
        out = CompressedImage(format='jpeg')
        out.header.stamp = self.get_clock().now().to_msg()
        out.data = cv2.imencode('.jpg', res.plot())[1].tobytes()
        self.pub_img.publish(out)


def main():
    rclpy.init()
    node = Detector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.try_shutdown()
