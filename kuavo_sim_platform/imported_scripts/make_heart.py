#!/usr/bin/env python3
"""比心手势 —— 用 14 维上肢关节轨迹在头顶前方做大爱心 (Kuavo 网页导入脚本)。

这个版本走 /kuavo_arm_traj 关节空间，不再走末端 IK。原因是头顶爱心
靠近工作空间边界，末端 IK 容易选到手臂绕到背后的分支；关节空间和
桌面工具“敬礼”动作一样，更能保证手臂实际抬起来。

用法
----
1. 网页导入本文件后选择运行即可，默认行为：
     - 仅 ArmOnly 模式，底盘不动；
     - 双臂用 14 维关节关键帧在头顶前方做爱心；
     - 做完后自动复位到中立姿态并切换 NoControl。
2. 进阶可在容器内命令行加参数：
     python3 make_heart.py --sweeps 2 --speed 0.6 --fingers

调参
----
所有关节/时序常量集中在下方 <<< 可调常量 >>> 区。5-W 的
/kuavo_arm_traj 使用角度量级，不是弧度。

安全
----
- 固定扫描次数，无无限循环；每步带 sleep；
- try/finally 保证异常时也复位手臂并切回 NoControl。
"""

import os
import sys
import time
import argparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from kuavo_sim import KuavoSim

# ======================== <<< 可调常量 >>> ========================
# 扫描参数
SWEEPS      = 2   # 完整描几遍爱心
WAYPOINT_DT = 0.16  # 每个关节插值点之间的间隔 (s)，受 --speed 缩放
STEPS_PER_SEGMENT = 8

# 灵巧手“放松张开”值 (0..100)，用于保持轮廓干净；如末端不是灵巧手会被忽略
HAND_OPEN_VALUE = 20

# 收尾点睛手势名称 (仅当 --fingers 时使用)；用 hand.get_gesture_names() 失败时自动跳过
FINGER_GESTURE = "ok"

# 14 维顺序按桌面工具/teach_pendant 的上肢顺序理解。
# 注意：桌面工具完整动作帧是 29 维：
#   left arm 7, right arm 7, left hand 6, right hand 6, head 2, waist 1。
# 这里只发前 14 维到 /kuavo_arm_traj。
#   左[pitch, roll, yaw, forearm, hand_yaw, hand_roll, hand_pitch]
#   右[pitch, roll, yaw, forearm, hand_yaw, hand_roll, hand_pitch]
ZERO_POSE = [0.0] * 14

# 这些关键帧使用 /kuavo_arm_traj 角度量级。右臂参考桌面工具里能把手举高的
# 姿态：pitch≈-180, roll≈-40, yaw≈90, forearm≈-80。
HEART_KEYFRAMES = [
    # 顶尖：双手尽量在头顶中线附近
    [-176, 40, -90, -86, 90, -54, 0,  -176, -40, 90, -86, -90, 54, 0],
    # 上瓣：双手向外上方打开一点
    [-166, 58, -72, -78, 72, -40, 0,  -166, -58, 72, -78, -72, 40, 0],
    # 外侧瓣：形成心形左右肩部，幅度控制在小范围
    [-150, 70, -48, -68, 48, -28, 0,  -150, -70, 48, -68, -48, 28, 0],
    # 下凹：回到中线但高度低于顶尖
    [-158, 46, -82, -92, 82, -46, 0,  -158, -46, 82, -92, -82, 46, 0],
]
# =================================================================


# -------------------- 辅助 --------------------
def _lerp_pose(a, b, alpha):
    return [
        round(float(x) + (float(y) - float(x)) * float(alpha), 3)
        for x, y in zip(a, b)
    ]


def _publish_arm(bot, joints, dt, wait_reach=False):
    since = time.time()
    bot.arm_joint(joints)
    if wait_reach:
        reached = bot.wait_arm_joint_reached(timeout=1.0, since=since)
        if reached is None:
            print("[make_heart] wait_arm_joint_reached 超时，继续", flush=True)
    if dt and dt > 0:
        time.sleep(dt)


def _move_between(bot, start, end, steps, dt, wait_reach=False):
    for i in range(1, int(steps) + 1):
        _publish_arm(
            bot,
            _lerp_pose(start, end, i / float(steps)),
            dt=dt,
            wait_reach=wait_reach,
        )


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
def run_heart(bot, sweeps=SWEEPS, speed=1.0, fingers=False, frame=2, wait_reach=False):
    """核心动作序列。调用方需已进入 with KuavoSim() 块。"""
    dt = WAYPOINT_DT / max(0.2, speed)

    # 1) 只动手臂
    bot.set_mode_arm_only()
    bot.set_arm_control_mode(2)  # 外部控制器，允许下发 /kuavo_arm_traj
    time.sleep(0.5)

    # 2) 灵巧手放松
    _maybe_open_hands(bot)

    # 3) 上举到起始顶尖
    print("[make_heart] 使用关节空间轨迹，不走末端 IK (frame 参数已忽略)")
    print("[make_heart] 抬到头顶顶尖...")
    _move_between(bot, ZERO_POSE, HEART_KEYFRAMES[0], STEPS_PER_SEGMENT,
                  dt=dt, wait_reach=wait_reach)

    # 4) 心形扫描：顶尖 -> 上瓣 -> 外侧 -> 下凹，再反向回顶尖
    for s in range(sweeps):
        print("[make_heart] 第 %d/%d 遍描心..." % (s + 1, sweeps))
        path = HEART_KEYFRAMES
        if s % 2 == 1:
            path = list(reversed(HEART_KEYFRAMES))
        for a, b in zip(path, path[1:]):
            _move_between(bot, a, b, STEPS_PER_SEGMENT,
                          dt=dt, wait_reach=wait_reach)

    # 6) 下凹处保持
    print("[make_heart] 保持当前姿态 ~1s")
    time.sleep(1.0)
    if fingers:
        _maybe_finger_flourish(bot)

    # 7) 回到顶尖 (两手重新在头顶并拢收拢)
    print("[make_heart] 回到顶尖...")
    _move_between(bot, HEART_KEYFRAMES[-1], HEART_KEYFRAMES[0], STEPS_PER_SEGMENT,
                  dt=dt, wait_reach=wait_reach)
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
                    help="兼容旧版末端 IK 脚本的参数；当前关节空间版本会忽略")
    ap.add_argument("--wait-reach", action="store_true",
                    help="每个关节命令后等待 /lb_arm_joint_reach_time 反馈；默认不建议开启")
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
                             frame=args.frame,
                             wait_reach=args.wait_reach)
            print("[make_heart] 动作序列完成 ✓" if done
                  else "[make_heart] 未执行动作 (见上方日志)")
        finally:
            # 8) 安全收尾：无论如何都复位手臂 + 切回 NoControl
            try:
                bot.arm_joint([0.0] * 14)
                bot.wait_arm_joint_reached(timeout=10.0)
                print("[make_heart] 已 arm_joint 零位复位")
            except Exception as e:
                print("[make_heart] arm_joint 零位复位失败 (已忽略): %s" % e)
            try:
                bot.set_mode_no_control()
                print("[make_heart] 已切换 NoControl")
            except Exception as e:
                print("[make_heart] set_mode_no_control 失败 (已忽略): %s" % e)


if __name__ == "__main__":
    main()
