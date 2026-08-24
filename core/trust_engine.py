"""
trust_engine.py · 信任值计算引擎 v3.1
==========================================
实现智能论 v3.1 第2.9节的信任值四维结构算法。

信任 = ⟨P_trust, T_pred, T_context, E_weight⟩

T_total = 0.50·T_pred + 0.05·T_init + 0.05·T_relation + 0.05·T_value + 0.35·P_trust

供编译器验证单元和 LLM 桥接层调用。
"""

import time
import math
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field


# =============================================================================
# 数据结构
# =============================================================================

@dataclass
class TrustState:
    """信任状态快照"""
    P_trust: float = 0.5        # 统计基础信任
    T_pred: float = 0.5         # 预测信任
    T_init: float = 0.5          # 初始先验
    T_relation: float = 0.5      # 关系加权
    T_value: float = 0.5         # 价值一致性
    E_weight: float = 0.0        # 情感权重（二阶变化率）
    T_total: float = 0.5         # 综合信任值
    P_gap: float = 0.5           # 信息差置信
    timestamp: float = field(default_factory=time.time)


@dataclass
class TrustConfig:
    """信任计算配置参数"""
    # 综合信任权重
    w_pred: float = 0.50
    w_init: float = 0.05
    w_relation: float = 0.05
    w_value: float = 0.05
    w_P_trust: float = 0.35

    # P_trust 参数
    N_base: int = 30              # 默认观察窗口
    N_min: int = 20
    N_max: int = 50
    delta_threshold: float = 0.15  # δ_norm 阈值

    # T_pred 参数
    w_D1: float = 0.40           # 信息差缩小趋势
    w_D2: float = 0.20           # 可信边界声明一致性
    w_D3: float = 0.25           # 预期结果验证通过率
    w_D4: float = 0.15           # 协作平衡度

    # 稳定红利
    stability_bonus_max: float = 0.10
    stability_bonus_rate: float = 0.01
    stability_window: int = 30

    # 情感权重
    eta: float = 0.20            # E_weight 影响系数

    # 完全可信判定
    full_trust_threshold: float = 0.95
    full_trust_window: int = 30


# =============================================================================
# 信任引擎
# =============================================================================

class TrustEngine:
    """
    信任值计算引擎
    
    核心方法：
    - update_P_trust(deviations): 基于偏差历史更新 P_trust
    - compute_T_pred(info_gap_history): 计算预测信任
    - compute_T_total(state, config): 计算综合信任
    - check_full_trust(state, history): 检查是否达到完全可信
    - update_E_weight(state, history): 更新情感权重
    """

    def __init__(self, config: TrustConfig = None):
        self.config = config or TrustConfig()
        self.history: List[Dict] = []
        self.max_history: int = 500
        self._stability_counter: int = 0

    # -------------------------------------------------------------------------
    # P_trust：统计基础信任
    # -------------------------------------------------------------------------

    def update_P_trust(self, deviations: List[float]) -> float:
        """
        更新 P_trust = P(δ_norm < θ | 最近N轮)
        
        Args:
            deviations: 最近N轮的 δ_norm 值列表
            
        Returns:
            更新后的 P_trust 值
        """
        cfg = self.config
        N_eff = self._compute_N_effective(deviations)

        # 取最近 N_eff 轮
        recent = deviations[-N_eff:] if len(deviations) >= N_eff else deviations
        if not recent:
            return 0.5

        # 计算 δ_norm < θ 的比例
        within_threshold = sum(1 for d in recent if d < cfg.delta_threshold)
        P_trust = within_threshold / len(recent)

        return P_trust

    def _compute_N_effective(self, deviations: List[float]) -> int:
        """动态窗口校准"""
        cfg = self.config
        if len(deviations) < 5:
            return cfg.N_base

        # 基于交互频率估算（简化为偏差列表长度的函数）
        freq_factor = min(1.5, max(0.5, len(deviations) / cfg.N_base))
        N_eff = int(cfg.N_base * freq_factor)
        return max(cfg.N_min, min(cfg.N_max, N_eff))

    # -------------------------------------------------------------------------
    # T_pred：预测信任
    # -------------------------------------------------------------------------

    def compute_T_pred(self, info_gap_history: List[float],
                       boundary_consistency: float = 0.5,
                       verification_rate: float = 0.5,
                       balance_score: float = 0.5) -> float:
        """
        计算 T_pred = w1·D1 + w2·D2 + w3·D3 + w4·D4
        
        Args:
            info_gap_history: 最近信息差历史
            boundary_consistency: 可信边界声明一致性 [0,1]
            verification_rate: 预期结果验证通过率 [0,1]
            balance_score: 协作平衡度 [0,1]
            
        Returns:
            T_pred 值 [0,1]
        """
        cfg = self.config

        # D1: 信息差缩小趋势
        D1 = self._compute_D1(info_gap_history)

        # D2: 可信边界声明一致性
        D2 = boundary_consistency

        # D3: 预期结果验证通过率
        D3 = verification_rate

        # D4: 协作平衡度
        D4 = balance_score

        T_pred = (cfg.w_D1 * D1 + cfg.w_D2 * D2 +
                  cfg.w_D3 * D3 + cfg.w_D4 * D4)

        # 稳定红利
        bonus = self._compute_stability_bonus()
        T_pred = min(1.0, T_pred + bonus)

        return max(0.0, T_pred)

    def _compute_D1(self, info_gap_history: List[float]) -> float:
        """信息差缩小趋势：比较前半段和后半段的平均信息差"""
        if len(info_gap_history) < 4:
            return 0.5

        half = len(info_gap_history) // 2
        first_half = info_gap_history[:half]
        second_half = info_gap_history[half:]

        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)

        # 缩小越多，D1 越高
        diff = avg_first - avg_second
        D1 = 0.5 + diff * 2.0  # 缩放因子
        return max(0.0, min(1.0, D1))

    def _compute_stability_bonus(self) -> float:
        """稳定红利：连续达标轮次的累积增益"""
        cfg = self.config
        if self._stability_counter >= cfg.stability_window:
            bonus = cfg.stability_bonus_rate * self._stability_counter
            return min(cfg.stability_bonus_max, bonus)
        return 0.0

    def _update_stability(self, delta_normalized: float):
        """更新稳定计数器"""
        if delta_normalized < self.config.delta_threshold:
            self._stability_counter += 1
        else:
            self._stability_counter = 0

    # -------------------------------------------------------------------------
    # T_context：结构上下文
    # -------------------------------------------------------------------------

    def compute_T_context(self, T_init: float, T_relation: float,
                          T_value: float) -> Dict[str, float]:
        """
        计算 T_context 三维分量
        
        Returns:
            包含 T_init, T_relation, T_value 的字典
        """
        return {
            "T_init": T_init,
            "T_relation": T_relation,
            "T_value": T_value,
        }

    # -------------------------------------------------------------------------
    # T_total：综合信任
    # -------------------------------------------------------------------------

    def compute_T_total(self, state: TrustState) -> float:
        """
        计算综合信任：
        T_total = 0.50·T_pred + 0.05·T_init + 0.05·T_relation + 0.05·T_value + 0.35·P_trust
        """
        cfg = self.config
        T_total = (cfg.w_pred * state.T_pred +
                   cfg.w_init * state.T_init +
                   cfg.w_relation * state.T_relation +
                   cfg.w_value * state.T_value +
                   cfg.w_P_trust * state.P_trust)

        # 情感权重作为二阶加速因子
        T_effective = T_total * (1 + cfg.eta * state.E_weight)
        return max(0.0, min(1.0, T_effective))

    # -------------------------------------------------------------------------
    # E_weight：情感权重
    # -------------------------------------------------------------------------

    def update_E_weight(self, T_total_history: List[float]) -> float:
        """
        计算情感权重 = T_total 的二阶变化率
        
        E_weight 衡量信任值变化的加速度。
        正值 = 信任加速增长（温暖、靠近、确认）
        负值 = 信任增长放缓或下降（关切、询问、校准）
        """
        if len(T_total_history) < 3:
            return 0.0

        # 一阶差分（变化率）
        diffs = [T_total_history[i] - T_total_history[i-1]
                 for i in range(1, len(T_total_history))]

        # 二阶差分（加速度）
        if len(diffs) >= 2:
            second_diffs = [diffs[i] - diffs[i-1]
                           for i in range(1, len(diffs))]
            E_weight = sum(second_diffs) / len(second_diffs)
        else:
            E_weight = diffs[-1] if diffs else 0.0

        # 限制范围 [-0.1, 0.1]
        return max(-0.1, min(0.1, E_weight))

    # -------------------------------------------------------------------------
    # 完全可信判定
    # -------------------------------------------------------------------------

    def check_full_trust(self, P_trust: float, P_gap: float) -> bool:
        """
        双条件判定：P_trust ≥ 0.95 且 P_gap ≥ 0.95
        """
        cfg = self.config
        return (P_trust >= cfg.full_trust_threshold and
                P_gap >= cfg.full_trust_threshold)

    # -------------------------------------------------------------------------
    # P_gap：信息差置信
    # -------------------------------------------------------------------------

    def update_P_gap(self, D_norm_history: List[float]) -> float:
        """
        计算 P_gap = P(D_norm < 0.10 | 最近N轮)
        """
        cfg = self.config
        N = cfg.full_trust_window
        recent = D_norm_history[-N:] if len(D_norm_history) >= N else D_norm_history
        if not recent:
            return 0.5

        within = sum(1 for d in recent if d < 0.10)
        return within / len(recent)

    # -------------------------------------------------------------------------
    # 完整更新流程
    # -------------------------------------------------------------------------

    def full_update(self, deviations: List[float],
                   D_norm_history: List[float],
                   T_total_history: List[float],
                   boundary_consistency: float = 0.5,
                   verification_rate: float = 0.5,
                   balance_score: float = 0.5,
                   T_init: float = 0.5,
                   T_relation: float = 0.5,
                   T_value: float = 0.5) -> TrustState:
        """
        执行一次完整的信任值更新，返回新的 TrustState
        
        调用顺序：
        1. 更新 P_trust（基于偏差历史）
        2. 计算 T_pred（基于信息差历史）
        3. 更新 E_weight（基于 T_total 历史）
        4. 更新 P_gap（基于 D_norm 历史）
        5. 计算 T_total（综合所有分量）
        """
        # 1. P_trust
        P_trust = self.update_P_trust(deviations)

        # 2. T_pred
        T_pred = self.compute_T_pred(
            D_norm_history,
            boundary_consistency,
            verification_rate,
            balance_score
        )

        # 3. E_weight
        E_weight = self.update_E_weight(T_total_history)

        # 4. P_gap
        P_gap = self.update_P_gap(D_norm_history)

        # 5. 构建状态
        state = TrustState(
            P_trust=P_trust,
            T_pred=T_pred,
            T_init=T_init,
            T_relation=T_relation,
            T_value=T_value,
            E_weight=E_weight,
            P_gap=P_gap,
        )

        # 6. T_total
        state.T_total = self.compute_T_total(state)
        state.timestamp = time.time()

        # 7. 更新稳定计数器
        if D_norm_history:
            self._update_stability(D_norm_history[-1])

        # 8. 记录历史
        self._record(state)

        return state

    def _record(self, state: TrustState):
        """记录信任状态到历史"""
        self.history.append({
            "timestamp": state.timestamp,
            "P_trust": state.P_trust,
            "T_pred": state.T_pred,
            "T_total": state.T_total,
            "E_weight": state.E_weight,
            "P_gap": state.P_gap,
        })
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    # -------------------------------------------------------------------------
    # 报告
    # -------------------------------------------------------------------------

    def get_report(self) -> Dict:
        """获取信任引擎报告"""
        if not self.history:
            return {"status": "no_data", "trust_value": 0.5}

        latest = self.history[-1]
        return {
            "P_trust": round(latest["P_trust"], 3),
            "T_pred": round(latest["T_pred"], 3),
            "T_total": round(latest["T_total"], 3),
            "E_weight": round(latest["E_weight"], 4),
            "P_gap": round(latest["P_gap"], 3),
            "is_full_trust": self.check_full_trust(
                latest["P_trust"], latest["P_gap"]
            ),
            "stability_counter": self._stability_counter,
            "history_length": len(self.history),
        }


# =============================================================================
# 便捷函数
# =============================================================================

def create_trust_engine() -> TrustEngine:
    """创建默认信任引擎"""
    return TrustEngine(TrustConfig())


# =============================================================================
# 测试
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("信任引擎 v3.1 测试")
    print("=" * 60)

    engine = create_trust_engine()

    # 模拟 35 轮交互
    import random
    random.seed(42)

    deviations = []
    D_norm_history = []
    T_total_history = []

    for i in range(35):
        # 模拟：前10轮偏差较大，后25轮逐渐收敛
        if i < 10:
            dev = random.uniform(0.05, 0.25)
            d_norm = random.uniform(0.2, 0.6)
        else:
            dev = random.uniform(0.01, 0.10)
            d_norm = random.uniform(0.05, 0.20)

        deviations.append(dev)
        D_norm_history.append(d_norm)

        # 第一次更新需要至少3轮
        if i >= 2:
            T_total_history.append(engine.history[-1]["T_total"] if engine.history else 0.5)

        state = engine.full_update(
            deviations=deviations,
            D_norm_history=D_norm_history,
            T_total_history=T_total_history,
            boundary_consistency=min(0.9, 0.3 + i * 0.02),
            verification_rate=min(0.9, 0.3 + i * 0.02),
            balance_score=0.5 + (i / 35) * 0.3,
        )

        if i in [0, 9, 19, 34]:
            print(f"\n轮次 {i+1}:")
            print(f"  P_trust  = {state.P_trust:.3f}")
            print(f"  T_pred   = {state.T_pred:.3f}")
            print(f"  E_weight = {state.E_weight:.4f}")
            print(f"  P_gap    = {state.P_gap:.3f}")
            print(f"  T_total  = {state.T_total:.3f}")

    print(f"\n{'=' * 60}")
    print("最终报告：")
    report = engine.get_report()
    for k, v in report.items():
        print(f"  {k}: {v}")
    print(f"{'=' * 60}")
