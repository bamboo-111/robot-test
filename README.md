# robot-test[make_heart.py](https://github.com/user-attachments/files/29495083/make_heart.py)
#!/usr/bin/env python3
"""比心手势 —— 双臂在身前拼出大爱心轮廓 (Kuavo 网页导入脚本)。

用法
----
1. 网页导入本文件后选择运行即可，默认行为：
     - 仅 ArmOnly 模式，底盘不动；
     - 双臂同步扫出标准心形参数曲线 (左右各半边、镜像)，拼成完整爱心；
     - 做完后自动复位到中立姿态并切换 NoControl。
2. 进阶可在容器内命令行加参数：
     python3 make_heart.py --sweeps 2 --speed 0.6 --fingers

调参
----
所有几何/时序常量集中在下方 <<< 可调常量 >>> 区。首次试跑若提示某航点
IK 不可达，优先：调小 WIDTH / HEIGHT，或增大 FORWARD。

安全
----
- 先对全部航点做 IK 预检 (solve_ik)，任一点解不出就中止，绝不发送不可达位姿；
- 固定扫描次数，无无限循环；每步带 sleep + 到达等待；
- try/finally 保证异常时也复位手臂并切回 NoControl。
"""

import os
import sys
import time
import math
import argparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim

# ======================== <<< 可调常量 >>> ========================
# 心形在躯干本体坐标系 (frame=2) 下的放置
FORWARD  = 0.42   # body_x：手臂向前伸出距离 (m)，越大越远离身体
WIDTH    = 0.28   # 半宽：爱心左右最大展开的一半 (m)
HEIGHT   = 0.32   # 总高：爱心顶凹到顶尖的高度 (m)
Z_CENTER = 0.45   # body_z：爱心竖直中心 (m)，约胸口高度

# 扫描参数
N_WAYPOINTS = 24  # 单条心形边的航点数 (越大越平滑、越慢)
SWEEPS      = 2   # 完整描几遍爱心
WAYPOINT_DT = 0.18  # 每个航点之间的间隔 (s)，受 --speed 缩放

# 灵巧手“放松张开”值 (0..100)，用于保持轮廓干净；如末端不是灵巧手会被忽略
HAND_OPEN_VALUE = 20

# 收尾点睛手势名称 (仅当 --fingers 时使用)；用 hand.get_gesture_names() 失败时自动跳过
FINGER_GESTURE = "ok"
# =================================================================


# -------------------- 心形参数曲线 --------------------
def _heart_param(t):
    """标准心形参数曲线 (归一化)。

    返回 (x, y)，其中：
      x = 16·sin³(t)        ∈ [0, 16]   当 t∈[0,π]  (右半边)
      y = 13·cos(t) − 5·cos(2t) − 2·cos(3t) − cos(4t)
    特征点：
      t=0  -> (0, 5)        顶部凹陷
      t=π  -> (0, −17)      底部尖角
    归一化：x/16 ∈[0,1]、(y−5)/(−22)∈[0,1] 顶部到尖角。
    """
    x = 16.0 * (math.sin(t) ** 3)
    y = (13.0 * math.cos(t)
         - 5.0 * math.cos(2 * t)
         - 2.0 * math.cos(3 * t)
         - math.cos(4 * t))
    return x, y


def heart_waypoints(n=N_WAYPOINTS):
    """生成 n+1 个航点 (含两端)，s 从 0→1。

    s=0：两手在顶部凹陷汇合；s=1：在底部尖角汇合。
    每个航点返回 (left_pose, right_pose)，均为
    dict(xyz=[x,y,z], ypr=[yaw,pitch,roll])，本体坐标系。

    body_x = FORWARD                              (恒定)
    body_y = side · (|x|/16) · WIDTH               (左 +，右 −)
    body_z = Z_CENTER + (0.5 − ny) · HEIGHT         (ny=0 顶凹→z 最高，ny=1 尖角→z 最低)
    末端朝向：手掌大致朝向身体前方 (掌心相对/向内)。
    """
    pts = []
    for i in range(n + 1):
        s = i / n
        # 右臂：t∈[0,π]，x≥0；左臂：t∈[2π,π]，x≤0，镜像
        t_r = s * math.pi
        t_l = (2.0 - s) * math.pi

        xr, yr = _heart_param(t_r)
        xl, yl = _heart_param(t_l)

        # 归一化到 [0,1]（顶凹 y=5 为 0，尖角 y=−17 为 1）
        nx_r = (xr / 16.0) if xr >= 0 else (-xr / 16.0)
        ny_r = (yr - 5.0) / (-22.0)
        nx_l = (xl / 16.0) if xl >= 0 else (-xl / 16.0)
        ny_l = (yl - 5.0) / (-22.0)

        # 右臂 side=−1 (y 负方向)，左臂 side=+1 (y 正方向)
        # body_z：ny=0 顶凹→z 最高，ny=1 尖角→z 最低 (ROS body frame z 向上)
        bx = FORWARD
        r_xyz = [bx, -nx_r * WIDTH, Z_CENTER + (0.5 - ny_r) * HEIGHT]
        l_xyz = [bx,  nx_l * WIDTH, Z_CENTER + (0.5 - ny_l) * HEIGHT]

        # 掌心相对：偏航让手掌朝向身体中线
        # 右手 yaw>0 使其朝 −y(向左)，左手 yaw<0 使其朝 +y(向右)
        ypr_r = [0.6, 0.0, 0.0]
        ypr_l = [-0.6, 0.0, 0.0]

        right = {"xyz": [round(v, 4) for v in r_xyz], "ypr": ypr_r}
        left  = {"xyz": [round(v, 4) for v in l_xyz], "ypr": ypr_l}
        pts.append((left, right))
    return pts


# -------------------- 辅助 --------------------
def _fmt_pose(p):
    return "xyz=%s ypr=%s" % (p["xyz"], p["ypr"])


def _precheck(bot, pts, frame=2):
    """对每个航点做 IK 预检。全部可达返回 True，否则 False。

    solve_ik 返回值无法在离线确定结构，故做宽松判定：
    只要返回 None / 空 / False 视为不可达。返回 tuple/list/dict 一律视为 OK。
    """
    ok = True
    for i, (left, right) in enumerate(pts):
        try:
            res = bot.solve_ik(left, right, frame=frame)
        except Exception as e:
            print("[make_heart] IK 异常 @waypoint %d/%d: %s" % (i, len(pts) - 1, e))
            print("             left  %s" % _fmt_pose(left))
            print("             right %s" % _fmt_pose(right))
            ok = False
            break
        if res is None or res is False or (hasattr(res, "__len__") and len(res) == 0):
            print("[make_heart] IK 不可达 @waypoint %d/%d" % (i, len(pts) - 1))
            print("             left  %s" % _fmt_pose(left))
            print("             right %s" % _fmt_pose(right))
            ok = False
            break
    return ok


def _go(bot, left, right, frame, dt, reach_timeout):
    """发送一个双臂末端位姿目标并等待到达。"""
    bot.two_arm_hand_pose(left, right, frame=frame)
    if dt and dt > 0:
        time.sleep(dt)
    bot.wait_arm_ee_reached(timeout=reach_timeout)


def _maybe_open_hands(bot):
    """尝试把灵巧手设为放松张开；非灵巧手末端会被忽略。"""
    try:
        bot.hand_position(left=[HAND_OPEN_VALUE] * 6,
                          right=[HAND_OPEN_VALUE] * 6)
        print("[make_heart] 灵巧手已设为放松张开 (value=%d)" % HAND_OPEN_VALUE)
    except Exception as e:
        print("[make_heart] 跳过灵巧手张开 (可能末端非灵巧手): %s" % e)


def _maybe_finger_flourish(bot, gesture_name=FINGER_GESTURE):
    """收尾点睛：在底部尖角做一次灵巧手内置手势。失败则静默跳过。"""
    try:
        # 优先用 SDK 接口；若封装未暴露则交给官方 SDK
        if hasattr(bot, "make_gesture"):
            bot.make_gesture(l_gesture_name=gesture_name,
                             r_gesture_name=gesture_name)
        else:
            from kuavo_humanoid_sdk import KuavoSDK, DexterousHand
            if not KuavoSDK().Init():
                print("[make_heart] 手势点睛：SDK 初始化失败，跳过")
                return
            hand = DexterousHand()
            try:
                names = hand.get_gesture_names()
            except Exception:
                names = None
            if names and gesture_name not in names:
                print("[make_heart] 手势 '%s' 不在列表 %s 中，跳过" % (gesture_name, names))
                return
            hand.make_gesture(l_gesture_name=gesture_name,
                              r_gesture_name=gesture_name)
        time.sleep(1.0)
        print("[make_heart] 已做收尾点睛手势: %s" % gesture_name)
    except Exception as e:
        print("[make_heart] 收尾点睛失败 (已忽略): %s" % e)


# -------------------- 主流程 --------------------
def run_heart(bot, sweeps=SWEEPS, speed=1.0, fingers=False, frame=2):
    """核心动作序列。调用方需已进入 with KuavoSim() 块。"""
    dt = WAYPOINT_DT / max(0.2, speed)
    reach_timeout = 6.0

    # 1) 只动手臂
    bot.set_mode_arm_only()
    bot.set_arm_control_mode(2)  # 外部控制器，允许下发末端位姿
    time.sleep(0.5)

    # 2) 灵巧手放松
    _maybe_open_hands(bot)

    # 3) 生成 + 预检全部航点
    pts = heart_waypoints(N_WAYPOINTS)
    print("[make_heart] 生成 %d 航点，做 IK 预检 (frame=%d)..." % (len(pts), frame))
    if not _precheck(bot, pts, frame=frame):
        print("[make_heart] 预检未通过，中止 (未发送任何位姿)。请调小 WIDTH/HEIGHT 或增大 FORWARD。")
        return False
    print("[make_heart] 预检通过 ✓")

    # 4) 慢速到起始点 (顶部凹陷，两手并拢)
    start_l, start_r = pts[0]
    print("[make_heart] 抬到起始点 (顶部凹陷)...")
    _go(bot, start_l, start_r, frame, dt=0.0, reach_timeout=8.0)

    # 5) 心形扫描
    bottom_l, bottom_r = pts[-1]
    for s in range(sweeps):
        print("[make_heart] 第 %d/%d 遍描心..." % (s + 1, sweeps))
        rng = range(1, len(pts))
        # 偶数遍正向 (顶->底)，奇数遍反向 (底->顶)，让来回都成爱心
        if s % 2 == 1:
            rng = range(len(pts) - 1, -1, -1)
        for i in rng:
            _go(bot, pts[i][0], pts[i][1], frame, dt=dt, reach_timeout=reach_timeout)

    # 6) 底部尖角保持
    print("[make_heart] 底部尖角保持 ~1s")
    _go(bot, bottom_l, bottom_r, frame, dt=0.0, reach_timeout=4.0)
    time.sleep(1.0)
    if fingers:
        _maybe_finger_flourish(bot)

    # 7) 回到顶部点 (两手重新并拢收拢)
    print("[make_heart] 回到顶部点...")
    _go(bot, start_l, start_r, frame, dt=0.0, reach_timeout=8.0)
    return True


def main():
    ap = argparse.ArgumentParser(description="Kuavo 双臂比心手势")
    ap.add_argument("--sweeps", type=int, default=SWEEPS,
                    help="完整描几遍爱心 (默认 %d)" % SWEEPS)
    ap.add_argument("--speed", type=float, default=1.0,
                    help="速度倍率 (默认 1.0，越大越快，建议首次用 0.5~1.0)")
    ap.add_argument("--fingers", action="store_true",
                    help="到底部尖角时额外做灵巧手收尾点睛手势")
    ap.add_argument("--frame", type=int, default=2,
                    help="末端位姿坐标系 (默认 2=躯干本体)")
    args = ap.parse_args()

    if args.sweeps < 1:
        raise SystemExit("--sweeps 必须 >= 1")
    if args.speed <= 0:
        raise SystemExit("--speed 必须 > 0")

    with KuavoSim() as bot:
        bot.wait_ready(timeout=30.0)
        try:
            done = run_heart(bot,
                             sweeps=args.sweeps,
                             speed=args.speed,
                             fingers=args.fingers,
                             frame=args.frame)
            print("[make_heart] 动作序列完成 ✓" if done
                  else "[make_heart] 未执行动作 (见上方日志)")
        finally:
            # 8) 安全收尾：无论如何都复位手臂 + 切回 NoControl
            try:
                bot.arm_reset()
                print("[make_heart] 已 arm_reset")
            except Exception as e:
                print("[make_heart] arm_reset 失败 (已忽略): %s" % e)
            try:
                bot.set_mode_no_control()
                print("[make_heart] 已切换 NoControl")
            except Exception as e:
                print("[make_heart] set_mode_no_control 失败 (已忽略): %s" % e)


if __name__ == "__main__":
    main()
