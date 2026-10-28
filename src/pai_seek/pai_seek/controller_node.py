"""検出結果と LiDAR を見て、目標物体を 探す → 近づく → (止まる / ついていく) ノード。

モード（パラメータ mode、または /mode トピックで切替）
  approach : 目標の手前 stop_distance で止まって終わり
  follow   : 目標との距離を follow_distance に保ち続ける（人が動けばついていく）
  stop     : その場で待機

状態
  SEARCH   : その場で回転して探す（最後に見えた方向へ回る）
  APPROACH : カメラの検出位置で向きを直しながら前進
  CLOSE    : 近すぎて足しか映らず YOLO が見失ったとき、LiDAR で正面付近の一番近い物体に寄る
  ARRIVED  : (approach) 到着して停止
  FOLLOW   : (follow) 距離を保つ。離れたら追う・近すぎたら下がる・ちょうどよければ待つ
  WAIT     : (stop) 待機
  FACE     : 一周しても見つからないとき、すぐ近く（1.8m 以内）の物の方を向く
  BACKOFF  : そのまま下がって距離をあけ、全身が映るようにしてから探し直す

subscribe: /detections (String JSON), /scan (LaserScan), /target (String), /mode (String)
publish:   /cmd_vel (Twist), /seek/state (String)
"""
import json
import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String

SEARCH, APPROACH, CLOSE, ARRIVED, FOLLOW, WAIT, FACE, BACKOFF = \
    'SEARCH', 'APPROACH', 'CLOSE', 'ARRIVED', 'FOLLOW', 'WAIT', 'FACE', 'BACKOFF'
MODES = ('approach', 'follow', 'stop')


class Controller(Node):
    def __init__(self):
        super().__init__('controller')
        p = self.declare_parameter
        p('target', 'person')
        p('mode', 'follow')
        p('stop_distance', 0.6)     # [m] approach: 前方がこれより近ければ停止
        p('follow_distance', 1.0)   # [m] follow: 保ちたい距離
        p('follow_deadband', 0.15)  # [m] follow: この範囲内なら動かない
        p('search_speed', 0.4)      # [rad/s] 探すときの回転速度
        p('forward_speed', 0.18)    # [m/s] 前進の最大速度
        p('back_speed', 0.08)       # [m/s] 近すぎるときに下がる速度
        p('k_turn', 0.8)            # カメラでの向き補正ゲイン
        p('k_lidar', 1.0)           # LiDAR での向き補正ゲイン
        p('k_dist', 0.5)            # follow: 距離の誤差 → 速度のゲイン
        p('lost_timeout', 1.5)      # [s] カメラで見失ったとみなすまでの時間
        p('close_range', 1.5)       # [m] LiDAR で「近くにいる」とみなす距離
        p('close_fov_deg', 35.0)    # [deg] LiDAR が目標を探す正面の範囲（±）
        p('backoff_trigger', 1.8)   # [m] 一周しても見つからないとき、これより近い物があれば下がって見直す
        p('backoff_distance', 2.4)  # [m] 下がって、正面の物とこの距離をあける（全身が映る距離）
        p('backoff_speed', 0.12)    # [m/s]

        self.target = self.get_parameter('target').value
        self.mode = self.get_parameter('mode').value
        self.state = WAIT if self.mode == 'stop' else SEARCH
        self.det = None
        self.det_time = None
        self.last_cx = 0.0
        self.last_h = 0.0
        self.front = math.inf
        self.near = None            # (距離, 角度[rad]) 正面 ±close_fov の最も近い点
        self.no_near_ticks = 0
        self.nearest = None         # (距離, 角度) 全周で一番近い点
        self.rear = math.inf        # 真後ろ ±30° の最短距離（下がるときの安全確認）
        self.state_time = self.get_clock().now()

        self.create_subscription(String, '/detections', self.on_det, 10)
        self.create_subscription(LaserScan, '/scan', self.on_scan, qos_profile_sensor_data)
        self.create_subscription(String, '/target', self.on_target, 10)
        self.create_subscription(String, '/mode', self.on_mode, 10)
        self.pub_cmd = self.create_publisher(Twist, '/cmd_vel', 10)
        self.pub_state = self.create_publisher(String, '/seek/state', 10)
        self.create_timer(0.1, self.tick)
        self.get_logger().info(f'target = {self.target}, mode = {self.mode}')

    def P(self, name):
        return self.get_parameter(name).value

    def set_state(self, s):
        if s != self.state:
            self.get_logger().info(f'{self.state} -> {s}')
            self.state = s
            self.state_time = self.get_clock().now()

    def state_age(self):
        return (self.get_clock().now() - self.state_time).nanoseconds * 1e-9

    # ---- callbacks ----
    def on_target(self, msg):
        self.target = msg.data.strip()
        self.det, self.det_time, self.last_h = None, None, 0.0
        self.get_logger().info(f'new target = {self.target}')
        if self.mode != 'stop':
            self.set_state(SEARCH)

    def on_mode(self, msg):
        m = msg.data.strip()
        if m not in MODES:
            self.get_logger().warn(f'unknown mode: {m} (use {MODES})')
            return
        self.mode = m
        self.get_logger().info(f'new mode = {m}')
        self.set_state(WAIT if m == 'stop' else SEARCH)

    def on_det(self, msg):
        cands = [d for d in json.loads(msg.data) if d['cls'] == self.target]
        if cands:
            self.det = max(cands, key=lambda d: d['conf'])
            self.det_time = self.get_clock().now()
            self.last_cx, self.last_h = self.det['cx'], self.det['h']

    def on_scan(self, msg):
        front_lim = math.radians(15)
        close_lim = math.radians(self.P('close_fov_deg'))
        front, near, nearest, rear = math.inf, None, None, math.inf
        for i, r in enumerate(msg.ranges):
            if not (msg.range_min < r < msg.range_max):
                continue
            a = msg.angle_min + i * msg.angle_increment
            a = math.atan2(math.sin(a), math.cos(a))   # -pi..pi, 0 = 正面, 正 = 左
            if abs(a) <= front_lim:
                front = min(front, r)
            if abs(a) <= close_lim and (near is None or r < near[0]):
                near = (r, a)
            if nearest is None or r < nearest[0]:
                nearest = (r, a)
            if abs(a) >= math.radians(150):
                rear = min(rear, r)
        self.front, self.near, self.nearest, self.rear = front, near, nearest, rear

    def seen_recently(self):
        if self.det_time is None:
            return False
        age = (self.get_clock().now() - self.det_time).nanoseconds * 1e-9
        return age < self.P('lost_timeout')

    # ---- 動作 ----
    def heading(self, seen):
        """向きの補正量と、向きが合っているか。カメラで見えていればカメラ、なければ LiDAR。"""
        if seen:
            return -self.P('k_turn') * self.det['cx'], abs(self.det['cx']) < 0.3
        _, a = self.near
        return self.P('k_lidar') * a, abs(a) < 0.3

    def tick(self):
        cmd = Twist()
        seen = self.seen_recently()
        near_ok = self.near is not None and self.near[0] <= self.P('close_range')
        # LiDAR で近くに何もない状態が続いた回数（ばたつき防止）
        self.no_near_ticks = 0 if near_ok else self.no_near_ticks + 1

        if self.state == SEARCH:
            full_turn = 2 * math.pi / self.P('search_speed') * 1.1   # 一周にかかる時間（少し余裕）
            if seen:
                self.set_state(APPROACH)
            elif self.state_age() > full_turn and self.nearest is not None \
                    and self.nearest[0] < self.P('backoff_trigger'):
                # 一周しても見つからないが、すぐ近くに何かある
                # = 近すぎて足しか映らず検出できていない可能性 → そちらを向いて下がり、見直す
                self.set_state(FACE)
            else:
                direction = -1.0 if self.last_cx > 0 else 1.0   # 最後に見えた方向へ回る
                cmd.angular.z = direction * self.P('search_speed')

        elif self.state == FACE:
            if seen:
                self.set_state(APPROACH)
            elif self.nearest is None or self.state_age() > 15.0:
                self.set_state(SEARCH)
            else:
                a = self.nearest[1]
                cmd.angular.z = max(-0.6, min(0.6, self.P('k_lidar') * a))
                if abs(a) < 0.15:
                    self.set_state(BACKOFF)

        elif self.state == BACKOFF:
            far_enough = self.near is None or self.near[0] >= self.P('backoff_distance')
            if seen:
                self.set_state(APPROACH)
            elif far_enough or self.rear < 0.4 or self.state_age() > 20.0:
                self.set_state(SEARCH)     # 下がり終えた（または後ろが近い）→ もう一度探す
            else:
                cmd.linear.x = -self.P('backoff_speed')
                if self.near is not None:  # 正面の物の方を向いたまま下がる
                    cmd.angular.z = max(-0.4, min(0.4, self.P('k_lidar') * self.near[1]))

        elif self.state == APPROACH:
            if self.mode == 'follow' and near_ok and seen:
                self.set_state(FOLLOW)
            elif self.mode == 'approach' and self.front < self.P('stop_distance'):
                self.arrive()
            elif not seen:
                self.set_state(CLOSE if near_ok else SEARCH)
            else:
                cmd.angular.z, aligned = self.heading(True)
                if aligned:
                    cmd.linear.x = self.P('forward_speed')

        elif self.state == CLOSE:
            if self.mode == 'follow' and near_ok:
                self.set_state(FOLLOW)
            elif self.front < self.P('stop_distance'):
                self.arrive()
            elif self.no_near_ticks >= 10:
                self.set_state(SEARCH)
            elif near_ok:
                cmd.angular.z, aligned = self.heading(False)
                if aligned:
                    cmd.linear.x = self.P('forward_speed') * 0.7

        elif self.state == FOLLOW:
            if not seen and self.no_near_ticks >= 10:
                self.set_state(SEARCH)          # カメラでも LiDAR でも見失った
            elif not near_ok:
                # 遠ざかった（LiDAR の範囲外）がカメラでは見えている → 追いかける
                if seen:
                    cmd.angular.z, aligned = self.heading(True)
                    if aligned:
                        cmd.linear.x = self.P('forward_speed')
            else:
                cmd.angular.z, aligned = self.heading(seen)
                err = self.near[0] - self.P('follow_distance')
                if err > self.P('follow_deadband') and aligned:
                    cmd.linear.x = min(self.P('forward_speed'), self.P('k_dist') * err)
                elif err < -self.P('follow_deadband'):
                    cmd.linear.x = -self.P('back_speed')
                elif abs(cmd.angular.z) < 0.05:
                    cmd.angular.z = 0.0          # ちょうどよい距離・向き → 待つ

        # ARRIVED / WAIT は何もしない（cmd = 0）
        self.pub_cmd.publish(cmd)
        near = f'{self.near[0]:.2f}m@{math.degrees(self.near[1]):.0f}deg' if self.near else '-'
        self.pub_state.publish(String(
            data=f'{self.state} mode={self.mode} target={self.target} '
                 f'front={self.front:.2f} near={near} seen={seen}'))

    def arrive(self):
        self.set_state(ARRIVED)
        self.get_logger().info(f'arrived at {self.target} ({self.front:.2f} m)')


def main():
    rclpy.init()
    node = Controller()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.pub_cmd.publish(Twist())
    node.destroy_node()
    rclpy.try_shutdown()
