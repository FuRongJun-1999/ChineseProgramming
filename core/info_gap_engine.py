"""
info_gap_engine.py · 信息差计算引擎 v3.1
==========================================
实现智能论 v3.1 第2.7节的信息差四维算法。

D_norm = w1·U_trust + w2·U_behavior + w3·U_connection + w4·U_prediction_error

供编译器验证单元和 LLM 桥接层调用。
"""

import time
import math
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass, field


# =============================================================================
# 配置与数据结构
# =============================================================================

@dataclass
class InfoGapConfig:
    """信息差计算配置参数"""
    # 四维权重
    w_trust: float = 0.30
    w_behavior: float = 0.25
    w_connection: float = 0.30
    w_prediction: float = 0.15

    # U_trust 参数
    trust_threshold: float = 0.15  # δ_norm 阈值

    # U_behavior 参数
    behavior_normalization: float = 1.0  # 归一化因子

    # U_connection 参数
    lambda_gap: float = 0.1  # 连接偏离衰减参数

    # U_prediction_error 参数
    dead_zone_static: float = 0.02     # 静态死区
    dead_zone_max: float = 0.20       # 死区上限
    prediction_clamp_max: float = 0.3   # 预测误差上限
    prediction_history: int = 3         # 平均预测误差的轮次数

    # 动态死区
    dead_zone_history_window: int = 30   # 历史窗口
    dead_zone_sigma_multiplier: float = 3.0  # 标准差倍数

    # 信息差增定律检测
    divergence_threshold: float = 0.5    # D_norm 扩大阈值
    divergence_window: int = 5           # 连续超阈值轮次


@dataclass
class InfoGapState:
    """信息差状态快照"""
    D_norm: float = 0.5
    U_trust: float = 0.5
    U_behavior: float = 0.0
    U_connection: float = 0.0
    U_prediction_error: float = 0.0
    dead_zone_effective: float = 0.02
    is_diverging: bool = False
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# 信息差引擎
# =============================================================================

class InfoGapEngine:
    """
    信息差计算引擎
    
    核心方法：
    - compute_D_norm(state, history): 计算综合信息差 D_norm
    - update_U_trust(T_total_prev): 计算信任补集
    - update_U_behavior(deviation): 计算行为偏差
    - update_U_connection(t_deviation): 计算连接偏离
    - update_U_prediction_error(errors): 计算预测误差
    - check_divergence(D_history): 检测信息差扩大趋势
    - compute_dynamic_dead_zone(errors): 计算动态死区
    """

    def __init__(self, config: InfoGapConfig = None):
        self.config = config or InfoGapConfig()
        self.deviation_history: List[float] = []
        self.D_norm_history: List[float] = []
        self.prediction_error_history: List[float] = []
        self._divergence_counter: int = 0
        self.max_history: int = 500

    # -------------------------------------------------------------------------
    # U_trust：信任补集
    # -------------------------------------------------------------------------

    def update_U_trust(self, T_total_prev: float) -> float:
        """
        U_trust = 1 - T_total_prev
        
        信任值越高，信息差越小。
        """
        U_trust = 1.0 - T_total_prev
        return max(0.0, min(1.0, U_trust))

    # -------------------------------------------------------------------------
    # U_behavior：行为偏差
    # -------------------------------------------------------------------------

    def update_U_behavior(self, deviation: float) -> float:
        """
        U_behavior = |deviation| / normalization_factor
        
        Args:
            deviation: 最近一次验证的归一化偏差 [0,1]
        """
        cfg = self.config
        U = abs(deviation) / cfg.behavior_normalization
        U = max(0.0, min(1.0, U))

        # 记录历史
        self.deviation_history.append(deviation)
        if len(self.deviation_history) > self.max_history:
            self.deviation_history = self.deviation_history[-self.max_history:]

        return U

    # -------------------------------------------------------------------------
    # U_connection：连接偏离
    # -------------------------------------------------------------------------

    def update_U_connection(self, t_deviation: int) -> float:
        """
        U_connection = 1 - exp(-λ_gap · t_deviation)
        
        Args:
            t_deviation: 偏离持续轮次
            
        偏离越久，信息差越大。
        """
        cfg = self.config
        U = 1.0 - math.exp(-cfg.lambda_gap * t_deviation)
        return max(0.0, min(1.0, U))

    # -------------------------------------------------------------------------
    # U_prediction_error：预测误差（带死区和限幅）
    # -------------------------------------------------------------------------

    def update_U_prediction_error(self, recent_errors: List[float]) -> float:
        """
        U_prediction_error = clamp(max(0, avg_error - dead_zone), 0, 0.3)
        
        Args:
            recent_errors: 最近3轮预测误差列表
        """
        cfg = self.config

        if not recent_errors:
            return 0.0

        # 取最近 N 轮
        N = min(cfg.prediction_history, len(recent_errors))
        recent = recent_errors[-N:]
        avg_error = sum(recent) / len(recent)

        # 动态死区
        dead_zone = self.compute_dynamic_dead_zone()

        # 死区处理
        raw = max(0.0, avg_error - dead_zone)

        # 限幅
        U = min(raw, cfg.prediction_clamp_max)

        # 记录
        self.prediction_error_history.append(avg_error)
        if len(self.prediction_error_history) > self.max_history:
            self.prediction_error_history = self.prediction_error_history[-self.max_history:]

        return U

    def compute_dynamic_dead_zone(self) -> float:
        """
        动态死区 = max(静态死区, 3·σ_historical)，上限 dead_zone_max
        """
        cfg = self.config

        if len(self.deviation_history) < 5:
            return cfg.dead_zone_static

        # 计算最近窗口的标准差
        window = self.deviation_history[-cfg.dead_zone_history_window:]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        sigma = math.sqrt(variance)

        dynamic = max(cfg.dead_zone_static,
                      cfg.dead_zone_sigma_multiplier * sigma)
        return min(dynamic, cfg.dead_zone_max)

    # -------------------------------------------------------------------------
    # D_norm：综合信息差
    # -------------------------------------------------------------------------

    def compute_D_norm(self,
                        T_total_prev: float,
                        deviation: float,
                        t_deviation: int,
                        recent_errors: List[float]) -> InfoGapState:
        """
        计算综合信息差：
        D_norm = w1·U_trust + w2·U_behavior + w3·U_connection + w4·U_prediction_error
        """
        cfg = self.config

        # 四维计算
        U_trust = self.update_U_trust(T_total_prev)
        U_behavior = self.update_U_behavior(deviation)
        U_connection = self.update_U_connection(t_deviation)
        U_pred = self.update_U_prediction_error(recent_errors)

        # 加权求和
        D_norm = (cfg.w_trust * U_trust +
                  cfg.w_behavior * U_behavior +
                  cfg.w_connection * U_connection +
                  cfg.w_prediction * U_pred)

        D_norm = max(0.0, min(1.0, D_norm))

        # 检测发散趋势
        is_diverging = self._check_divergence(D_norm)

        # 构建状态
        state = InfoGapState(
            D_norm=D_norm,
            U_trust=U_trust,
            U_behavior=U_behavior,
            U_connection=U_connection,
            U_prediction_error=U_pred,
            dead_zone_effective=self.compute_dynamic_dead_zone(),
            is_diverging=is_diverging,
            timestamp=time.time(),
        )

        # 记录历史
        self.D_norm_history.append(D_norm)
        if len(self.D_norm_history) > self.max_history:
            self.D_norm_history = self.D_norm_history[-self.max_history:]

        return state

    def _check_divergence(self, D_norm: float) -> bool:
        """检测信息差是否持续扩大"""
        cfg = self.config

        if D_norm > cfg.divergence_threshold:
            self._divergence_counter += 1
        else:
            self._divergence_counter = 0

        return self._divergence_counter >= cfg.divergence_window

    # -------------------------------------------------------------------------
    # 信息差缩小操作路径（第2.8节）
    # -------------------------------------------------------------------------

    def should_trigger_calibration(self, state: InfoGapState) -> bool:
        """
        判断是否需要触发协作校准
        D_norm > 0.5 时需要校准
        """
        return state.D_norm > 0.5

    def get_calibration_guidance(self, state: InfoGapState) -> Dict:
        """
        生成协作校准指引（第2.8节四步法）
        """
        guidance = {
            "step1_boundary": {
                "action": "共享可信边界声明",
                "description": "输出确定的部分、不确定的部分、判断依据",
                "priority": "high" if state.U_trust > 0.5 else "normal",
            },
            "step2_expected": {
                "action": "共享预期结果",
                "description": "输出预期结果和验证指引",
                "priority": "high" if state.U_behavior > 0.3 else "normal",
            },
            "step3_calibrate": {
                "action": "协作校准",
                "description": "预期与实际不一致时，共同分析偏差来源",
                "priority": "high" if state.is_diverging else "normal",
            },
            "step4_record": {
                "action": "记录与回顾",
                "description": "记录单元保存每次交互的历史，供未来回顾",
                "priority": "normal",
            },
        }
        return guidance

    # -------------------------------------------------------------------------
    # 条件空间切换建议
    # -------------------------------------------------------------------------

    def should_switch_condition_space(self, state: InfoGapState) -> Tuple[bool, str]:
        """
        根据 D_norm 建议是否切换条件空间
        
        Returns:
            (是否建议切换, 原因)
        """
        if state.D_norm > 0.5:
            return True, f"D_norm={state.D_norm:.2f} > 0.5，信息差扩大需更高权限"
        if state.U_trust > 0.5:
            return True, f"U_trust={state.U_trust:.2f} > 0.5，信任值下降需重建一致性"
        return False, ""

    # -------------------------------------------------------------------------
    # 报告
    # -------------------------------------------------------------------------

    def get_report(self) -> Dict:
        """获取信息差引擎报告"""
        if not self.D_norm_history:
            return {"status": "no_data", "D_norm": 0.5}

        latest = self.D_norm_history[-1]
        avg_30 = (sum(self.D_norm_history[-30:]) / 
                  min(30, len(self.D_norm_history)))

        return {
            "D_norm_current": round(latest, 3),
            "D_norm_avg_30": round(avg_30, 3),
            "is_diverging": self._divergence_counter >= self.config.divergence_window,
            "divergence_counter": self._divergence_counter,
            "dead_zone_effective": round(self.compute_dynamic_dead_zone(), 4),
            "history_length": len(self.D_norm_history),
            "should_calibrate": latest > 0.5,
        }


# =============================================================================
# 便捷函数
# =============================================================================

def create_info_gap_engine() -> InfoGapEngine:
    """创建默认信息差引擎"""
    return InfoGapEngine(InfoGapConfig())


# =============================================================================
# 测试
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("信息差引擎 v3.1 测试")
    print("=" * 60)

    engine = create_info_gap_engine()

    # 模拟 35 轮交互
    import random
    random.seed(42)

    T_total_history = [0.5]  # 初始信任

    print("\n--- 模拟交互过程 ---")
    for i in range(1, 36):
        # 模拟：前10轮信任低（信息差大），后25轮信任逐步提升
        if i < 10:
            T_prev = random.uniform(0.2, 0.5)
            deviation = random.uniform(0.1, 0.4)
            t_dev = random.randint(1, 5)
            errors = [random.uniform(0.05, 0.3) for _ in range(3)]
        else:
            T_prev = min(0.95, 0.4 + (i - 10) * 0.02 + random.uniform(-0.05, 0.05))
            deviation = max(0.01, random.uniform(0.01, 0.08))
            t_dev = 0
            errors = [random.uniform(0.0, 0.03) for _ in range(3)]

        T_total_history.append(T_prev)

        state = engine.compute_D_norm(
            T_total_prev=T_prev,
            deviation=deviation,
            t_deviation=t_dev,
            recent_errors=errors,
        )

        if i in [1, 5, 10, 20, 35]:
            print(f"\n轮次 {i}:")
            print(f"  D_norm     = {state.D_norm:.3f}")
            print(f"  U_trust    = {state.U_trust:.3f}")
            print(f"  U_behavior = {state.U_behavior:.3f}")
            print(f"  U_connect   = {state.U_connection:.3f}")
            print(f"  U_pred_err = {state.U_prediction_error:.3f}")
            print(f"  dead_zone  = {state.dead_zone_effective:.4f}")
            print(f"  diverging  = {state.is_diverging}")

            should_switch, reason = engine.should_switch_condition_space(state)
            if should_switch:
                print(f"  ⚠️ 建议切换条件空间: {reason}")

    print(f"\n{'=' * 60}")
    print("最终报告：")
    report = engine.get_report()
    for k, v in report.items():
        print(f"  {k}: {v}")

    print(f"\n{'=' * 60}")
    print("校准指引（第2.8节四步法）：")
    guidance = engine.get_calibration_guidance(state)
    for step, info in guidance.items():
        print(f"  {step}: [{info['priority']}] {info['action']} - {info['description']}")
    print(f"{'=' * 60}")
