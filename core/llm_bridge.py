"""
llm_bridge.py · LLM 桥接层 v1.0
作为协议接入节点（单次推理模式），为编译器提供语义辅助。

支持供应商：Kimi（首选）、DeepSeek（备选）、自定义（需声明后果）
预留灵魂层接口：SpiritLayerProxy（可选）

核心方法：
- understand(text, context) -> str : 语义理解
- suggest_verification(rule_text, context) -> dict : 验证建议
- explain_term(term, context) -> str : 术语解释

内部信任管理（不对外暴露）
自我诊断能力（供自维持系统调用）
"""

import os
import json
import time
import hashlib
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass, field
from enum import Enum
import requests

from .protocol_prompt import build_system_prompt, get_context_for_task


# =============================================================================
# 枚举与数据结构
# =============================================================================

class LLMProvider(Enum):
    """支持的 LLM 供应商"""
    KIMI = "kimi"
    DEEPSEEK = "deepseek"
    CUSTOM = "custom"


@dataclass
class ProviderConfig:
    """供应商连接配置"""
    provider: LLMProvider
    api_key: str
    base_url: str
    model: str
    recommended: bool = False

    @staticmethod
    def kimi(api_key: str = None) -> 'ProviderConfig':
        return ProviderConfig(
            provider=LLMProvider.KIMI,
            api_key=api_key or os.environ.get("KIMI_API_KEY", ""),
            base_url=os.environ.get("KIMI_BASE_URL", "https://api.moonshot.ai/v1"),
            model=os.environ.get("KIMI_MODEL", "kimi-k3"),
            recommended=True
        )

    @staticmethod
    def deepseek(api_key: str = None) -> 'ProviderConfig':
        return ProviderConfig(
            provider=LLMProvider.DEEPSEEK,
            api_key=api_key or os.environ.get("DEEPSEEK_API_KEY", ""),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            recommended=True
        )

    @staticmethod
    def custom(api_key: str, base_url: str, model: str) -> 'ProviderConfig':
        return ProviderConfig(
            provider=LLMProvider.CUSTOM,
            api_key=api_key,
            base_url=base_url,
            model=model,
            recommended=False
        )


@dataclass
class LLMCallRecord:
    """单次 LLM 调用的记录"""
    provider: str
    method: str
    success: bool
    latency: float
    input_length: int
    output_length: int
    error: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class LLMTrustMetrics:
    """本地信任指标（不依赖灵魂层）"""
    total_calls: int = 0
    successful_calls: int = 0
    total_latency: float = 0.0
    recent_failures: int = 0
    trust_value: float = 0.5  # 协议默认初始信任值
    consecutive_successes: int = 0

    def update_success(self, latency: float):
        self.total_calls += 1
        self.successful_calls += 1
        self.total_latency += latency
        self.recent_failures = 0
        self.consecutive_successes += 1
        # 成功时信任值微增（递减，避免无限增长）
        delta = 0.01 * (1 / (1 + self.consecutive_successes * 0.1))
        self.trust_value = min(1.0, self.trust_value + delta)

    def update_failure(self, error: str = ""):
        self.total_calls += 1
        self.recent_failures += 1
        self.consecutive_successes = 0
        # 失败时信任值下降，连续失败加速
        penalty = 0.03 * (1 + self.recent_failures * 0.5)
        self.trust_value = max(0.0, self.trust_value - penalty)

    def reliability(self) -> float:
        if self.total_calls == 0:
            return 0.5
        return self.successful_calls / self.total_calls

    def avg_latency(self) -> float:
        if self.successful_calls == 0:
            return 0.0
        return self.total_latency / self.successful_calls


# =============================================================================
# 灵魂层代理接口（预留）
# =============================================================================

class SpiritLayerProxy:
    """
    灵魂层代理抽象基类
    当前为空实现，供未来接入 spacetime-memory-engine 时继承
    """
    def get_context(self) -> Optional[Dict]:
        return None

    def report_llm_call(self, record: LLMCallRecord):
        pass

    def get_trust_threshold(self) -> float:
        return 0.3

    def should_use_llm(self) -> bool:
        return True


class NullSpiritLayer(SpiritLayerProxy):
    """空实现，无灵魂层时的默认行为"""
    pass


# =============================================================================
# 自我诊断
# =============================================================================

@dataclass
class DiagnosticReport:
    """自我诊断报告"""
    timestamp: float = field(default_factory=time.time)
    overall_status: str = "unknown"  # healthy / degraded / critical
    connected: bool = False
    primary_provider: str = ""
    fallback_provider: str = ""
    primary_trust: float = 0.0
    fallback_trust: float = 0.0
    total_calls: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp,
            "overall_status": self.overall_status,
            "connected": self.connected,
            "primary_provider": self.primary_provider,
            "fallback_provider": self.fallback_provider,
            "primary_trust": round(self.primary_trust, 3),
            "fallback_trust": round(self.fallback_trust, 3),
            "total_calls": self.total_calls,
            "success_rate": round(self.success_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "warnings": self.warnings,
            "errors": self.errors,
        }


# =============================================================================
# LLM 桥接层主类
# =============================================================================

class LLMBridge:
    """
    LLM 桥接层 —— 协议编译器语义辅助模块

    核心方法：
    - understand(text, context) -> str : 语义理解，返回结构化意图
    - suggest_verification(rule_text, context) -> dict : 验证建议
    - explain_term(term, context) -> str : 术语解释
    - diagnose() -> DiagnosticReport : 自我诊断

    特性：
    - 双供应商自动降级（Kimi → DeepSeek → Custom）
    - 本地信任计数器（协议默认 0.5 起算）
    - 灵魂层代理接口（可选）
    - 自我诊断（供自维持系统调用）
    """

    PROVIDER_PRIORITY = [LLMProvider.KIMI, LLMProvider.DEEPSEEK, LLMProvider.CUSTOM]

    def __init__(self,
                 primary: ProviderConfig = None,
                 fallback: ProviderConfig = None,
                 spirit_layer: SpiritLayerProxy = None,
                 auto_test: bool = True):
        """
        初始化 LLM 桥接层
        primary: 首选供应商（默认 Kimi）
        fallback: 备选供应商（默认 DeepSeek）
        spirit_layer: 灵魂层代理（可选，默认为空实现）
        auto_test: 是否在初始化时自动测试连接
        """
        self.primary = primary or ProviderConfig.kimi()
        self.fallback = fallback or ProviderConfig.deepseek()
        self.custom_providers: List[ProviderConfig] = []
        self.spirit = spirit_layer or NullSpiritLayer()

        # 本地信任指标（按供应商分别记录）
        self.metrics: Dict[str, LLMTrustMetrics] = {
            self.primary.provider.value: LLMTrustMetrics(),
            self.fallback.provider.value: LLMTrustMetrics(),
        }

        # 调用历史（用于调试和追溯）
        self.history: List[LLMCallRecord] = []
        self.max_history: int = 200

        # 连接状态
        self._connected: bool = False
        if auto_test:
            self._initialize_connection()

    # -------------------------------------------------------------------------
    # 初始化与连接管理
    # -------------------------------------------------------------------------

    def _initialize_connection(self):
        """初始化时测试连接并自动切换"""
        # 尝试首选
        if self._test_connection(self.primary):
            self._connected = True
            print(f"✅ LLM 桥接层已连接（首选: {self.primary.provider.value}）")
            return

        print(f"⚠️ 首选供应商 {self.primary.provider.value} 连接失败，尝试备选...")

        # 尝试备选
        if self._test_connection(self.fallback):
            self._connected = True
            # 交换主备
            self.primary, self.fallback = self.fallback, self.primary
            print(f"✅ 已切换至备选供应商 {self.primary.provider.value}")
            return

        print(f"❌ 所有推荐供应商均不可用")
        print(f"   Kimi:   {self._connection_status_text(ProviderConfig.kimi())}")
        print(f"   DeepSeek: {self._connection_status_text(ProviderConfig.deepseek())}")
        print(f"   编译器将在无 LLM 辅助模式下运行")
        print(f"   ⚠️ 后果：辞意/说故校验不可用，编译仅依赖规则驱动")

    def _connection_status_text(self, config: ProviderConfig) -> str:
        """获取连接状态文本"""
        if not config.api_key:
            return "未配置 API Key"
        if self._test_connection(config):
            return "✅ 可达"
        else:
            return "❌ 不可达"

    def reconnect(self) -> bool:
        """手动重连（供自维持系统调用）"""
        print(f"🔄 尝试重新连接 LLM 供应商...")
        self._initialize_connection()
        return self._connected

    # -------------------------------------------------------------------------
    # 公共方法
    # -------------------------------------------------------------------------

    def understand(self, text: str, context: Dict = None) -> Optional[str]:
        """
        语义理解 —— 将自然语言规则映射为结构化意图
        返回建议性结构映射（非终裁）
        """
        if not self._should_proceed("understand"):
            return None

        enhanced_context = self._merge_context(context)
        # 注入协议内核提示词 + 信任/信息差扩展
        task_ctx = get_context_for_task("understand")
        prompt = self._build_understanding_prompt(text, enhanced_context, task_ctx)

        return self._call_with_fallback(
            lambda cfg: self._raw_call_with_system(cfg, prompt, temperature=0.1),
            method="understand",
            input_length=len(text)
        )

    def suggest_verification(self, rule_text: str, context: Dict = None) -> Optional[Dict]:
        """
        验证意图辅助生成 —— 为验证单元提供建议
        验证单元保留终裁权
        """
        if not self._should_proceed("suggest_verification"):
            return None

        enhanced_context = self._merge_context(context)

        # 注入协议内核提示词 + 验证单元扩展
        task_ctx = get_context_for_task("verify")
        system_prompt = build_system_prompt(task_ctx.get("extensions", []))

        prompt = f"""{system_prompt}

---
你是一个协议验证辅助系统。分析以下规则，输出验证建议。

规则：{rule_text}
上下文：{json.dumps(enhanced_context, ensure_ascii=False)}

请输出 JSON 格式的验证建议：
{{
    "intended_meaning": "规则意图的自然语言描述",
    "expected_behavior": "预期行为",
    "edge_cases": ["边界情况1", "边界情况2"],
    "confidence": 0.0-1.0
}}"""

        response = self._call_with_fallback(
            lambda cfg: self._raw_call_with_system(cfg, prompt, temperature=0.2, json_mode=True),
            method="suggest_verification",
            input_length=len(rule_text)
        )

        if response:
            try:
                return json.loads(response)
            except json.JSONDecodeError:
                # 尝试提取 JSON 部分
                try:
                    start = response.index("{")
                    end = response.rindex("}") + 1
                    return json.loads(response[start:end])
                except (ValueError, json.JSONDecodeError):
                    return None
        return None

    def explain_term(self, term: str, context: str = "engineering") -> Optional[str]:
        """
        解释协议术语 —— 用于 CLI 的 explain 命令
        """
        if not self._should_proceed("explain_term"):
            return None

        # 注入协议内核提示词 + 术语扩展
        task_ctx = get_context_for_task("explain")
        system_prompt = build_system_prompt(task_ctx.get("extensions", []))

        prompt = f"""{system_prompt}

---
解释协议编译器中的术语 "{term}"。
上下文：{context}
请给出工程定义、使用示例和相关道德经投影（如有）。"""

        return self._call_with_fallback(
            lambda cfg: self._raw_call_with_system(cfg, prompt, temperature=0.3),
            method="explain_term",
            input_length=len(term)
        )

    # -------------------------------------------------------------------------
    # 自我诊断（供自维持系统调用）
    # -------------------------------------------------------------------------

    def diagnose(self) -> DiagnosticReport:
        """
        自我诊断 —— 返回当前健康状态报告
        供自维持系统（spacetime-memory-engine）定期调用
        """
        report = DiagnosticReport()

        # 基本状态
        report.primary_provider = self.primary.provider.value
        report.fallback_provider = self.fallback.provider.value
        report.connected = self._connected

        # 信任指标
        primary_metrics = self.metrics.get(self.primary.provider.value)
        fallback_metrics = self.metrics.get(self.fallback.provider.value)

        if primary_metrics:
            report.primary_trust = primary_metrics.trust_value
        if fallback_metrics:
            report.fallback_trust = fallback_metrics.trust_value

        # 汇总统计
        all_metrics = list(self.metrics.values())
        report.total_calls = sum(m.total_calls for m in all_metrics)
        total_success = sum(m.successful_calls for m in all_metrics)
        if report.total_calls > 0:
            report.success_rate = total_success / report.total_calls
        total_latency = sum(m.total_latency for m in all_metrics)
        if total_success > 0:
            report.avg_latency_ms = (total_latency / total_success) * 1000

        # 健康评估
        if not self._connected:
            report.overall_status = "critical"
            report.errors.append("所有 LLM 供应商均不可达")
            report.errors.append("编译器将在无 LLM 辅助模式下运行")
            report.errors.append("辞意/说故校验不可用")
        elif report.primary_trust < 0.3:
            report.overall_status = "degraded"
            report.warnings.append(f"首选供应商信任值过低: {report.primary_trust:.2f}")
            report.warnings.append("建议检查 API Key 有效性或切换供应商")
        elif report.success_rate < 0.7:
            report.overall_status = "degraded"
            report.warnings.append(f"整体成功率偏低: {report.success_rate:.1%}")
        else:
            report.overall_status = "healthy"

        # 供应商特定诊断
        for name, metrics in self.metrics.items():
            if metrics.total_calls > 0 and metrics.reliability() < 0.5:
                report.warnings.append(
                    f"供应商 {name} 可靠性低: {metrics.reliability():.1%} "
                    f"({metrics.successful_calls}/{metrics.total_calls})"
                )

        return report

    def get_trust_report(self) -> Dict:
        """获取各供应商的信任报告（内部使用）"""
        report = {}
        for provider, metrics in self.metrics.items():
            report[provider] = {
                "trust_value": round(metrics.trust_value, 3),
                "reliability": round(metrics.reliability(), 3),
                "avg_latency_ms": round(metrics.avg_latency() * 1000, 1),
                "total_calls": metrics.total_calls,
                "successful_calls": metrics.successful_calls,
                "consecutive_failures": metrics.recent_failures,
            }
        return report

    # -------------------------------------------------------------------------
    # 供应商管理
    # -------------------------------------------------------------------------

    def add_custom_provider(self, config: ProviderConfig):
        """添加自定义供应商（需明确后果）"""
        if not config.recommended:
            print(f"")
            print(f"⚠️⚠️⚠️ 警告：使用非推荐供应商 {config.provider.value}")
            print(f"   后果声明（根据盲区 74-revised）：")
            print(f"   1. 现象层同构性未验证，验证单元否决率可能上升")
            print(f"   2. 信任值按协议默认 0.5 起算")
            print(f"   3. 信息差评估噪声增大")
            print(f"   4. MCP 兼容性需自行保证")
            print(f"   推荐供应商：Kimi（首选）、DeepSeek（备选）")
            print(f"")
        self.custom_providers.append(config)
        self.metrics[config.provider.value] = LLMTrustMetrics()

    def set_primary(self, provider_name: str) -> bool:
        """手动切换首选供应商"""
        if provider_name == self.primary.provider.value:
            return True

        # 在备选或自定义中查找
        if provider_name == self.fallback.provider.value:
            self.primary, self.fallback = self.fallback, self.primary
            return True

        for i, cfg in enumerate(self.custom_providers):
            if cfg.provider.value == provider_name:
                self.primary = cfg
                self.custom_providers.pop(i)
                return True

        return False

    # -------------------------------------------------------------------------
    # 内部方法
    # -------------------------------------------------------------------------

    def _should_proceed(self, method: str) -> bool:
        """检查是否应该继续（灵魂层允许 + 有可用供应商）"""
        if not self.spirit.should_use_llm():
            return False
        if not self._connected:
            return False
        return True

    def _merge_context(self, context: Dict = None) -> Dict:
        """合并灵魂层上下文和调用方上下文"""
        spirit_ctx = self.spirit.get_context() or {}
        user_ctx = context or {}
        merged = {**spirit_ctx, **user_ctx}
        return merged

    def _call_with_fallback(self, call_fn: Callable, method: str,
                             input_length: int) -> Optional[str]:
        """
        带降级路径的调用：
        1. 尝试首选供应商
        2. 失败则尝试备选
        3. 再失败则尝试自定义供应商
        4. 全部失败则返回 None
        """
        providers_to_try = [
            (self.primary, self.primary.provider.value),
            (self.fallback, self.fallback.provider.value),
        ] + [(cfg, cfg.provider.value) for cfg in self.custom_providers]

        last_error = ""

        for config, provider_name in providers_to_try:
            if not config.api_key:
                continue

            # 检查本地信任值是否低于阈值
            threshold = self.spirit.get_trust_threshold()
            metrics = self.metrics.get(provider_name)
            if metrics and metrics.trust_value < threshold:
                print(f"⏭️ 跳过供应商 {provider_name}"
                      f"（信任值过低: {metrics.trust_value:.2f} < {threshold}）")
                continue

            start = time.time()
            try:
                result = call_fn(config)
                latency = time.time() - start
                output_length = len(result) if result else 0

                # 记录
                record = LLMCallRecord(
                    provider=provider_name,
                    method=method,
                    success=result is not None,
                    latency=latency,
                    input_length=input_length,
                    output_length=output_length,
                    timestamp=time.time()
                )
                self._add_history(record)

                if result is not None:
                    metrics = self.metrics[provider_name]
                    metrics.update_success(latency)
                    self.spirit.report_llm_call(record)
                    return result
                else:
                    metrics = self.metrics[provider_name]
                    metrics.update_failure("empty_result")
                    last_error = f"{provider_name}: 返回空结果"

            except Exception as e:
                latency = time.time() - start
                record = LLMCallRecord(
                    provider=provider_name,
                    method=method,
                    success=False,
                    latency=latency,
                    input_length=input_length,
                    output_length=0,
                    error=str(e),
                    timestamp=time.time()
                )
                self._add_history(record)

                metrics = self.metrics[provider_name]
                metrics.update_failure(str(e))
                self.spirit.report_llm_call(record)
                last_error = f"{provider_name}: {e}"
                print(f"❌ 供应商 {provider_name} 调用异常: {e}")

        # 全部失败
        print(f"⚠️ 所有 LLM 供应商不可用（{method}）")
        if last_error:
            print(f"   最后错误: {last_error}")
        print(f"   编译器将在无 LLM 辅助模式下继续")
        return None

    def _add_history(self, record: LLMCallRecord):
        """添加调用记录（限制大小）"""
        self.history.append(record)
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def _raw_call(self, config: ProviderConfig, prompt: str,
                  temperature: float = 0.1, max_tokens: int = 2048,
                  json_mode: bool = False) -> Optional[str]:
        """原始 API 调用（OpenAI 兼容格式，单 message）"""
        return self._raw_call_with_system(
            config, prompt,
            system_prompt=None,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode
        )

    def _raw_call_with_system(self, config: ProviderConfig, prompt: str,
                              system_prompt: str = None,
                              temperature: float = 0.1, max_tokens: int = 2048,
                              json_mode: bool = False) -> Optional[str]:
        """原始 API 调用（OpenAI 兼容格式，支持 system + user 双消息）"""
        if not config.api_key:
            return None

        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json"
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = requests.post(
                f"{config.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                print(f"   API 错误 [{config.provider.value}]: "
                      f"{resp.status_code} - {resp.text[:200]}")
                return None
        except requests.exceptions.Timeout:
            print(f"   ⏱️ [{config.provider.value}] 请求超时（60s）")
            return None
        except requests.exceptions.ConnectionError:
            print(f"   🔌 [{config.provider.value}] 连接失败")
            return None
        except Exception as e:
            raise  # 由 _call_with_fallback 捕获

    def _test_connection(self, config: ProviderConfig) -> bool:
        """测试供应商连通性"""
        if not config.api_key:
            return False
        try:
            result = self._raw_call(config, "ping", temperature=0.0, max_tokens=5)
            return result is not None
        except:
            return False

    def _build_understanding_prompt(self, text: str, context: Dict, task_ctx: Dict = None) -> str:
        """构建语义理解提示词（注入协议内核）"""
        # 构建系统提示词
        ext_list = (task_ctx or {}).get("extensions", [])
        system_prompt = build_system_prompt(ext_list)

        base = f"""{system_prompt}

---
你是一个协议编译器的语义理解模块。分析以下协议源代码片段，输出结构化理解。

源代码：{text}
"""
        if context:
            base += f"\n上下文：{json.dumps(context, ensure_ascii=False)}\n"

        base += """请输出：
1. 声明的协议路径（如有）
2. 定义的规则和条件
3. 引用的助记符及其含义
4. 可能的歧义点"""
        return base


# =============================================================================
# 便捷工厂函数
# =============================================================================

def create_default_bridge(spirit_layer: SpiritLayerProxy = None,
                         auto_test: bool = True) -> LLMBridge:
    """
    创建默认 LLM 桥接层
    环境变量配置：
    - KIMI_API_KEY / KIMI_BASE_URL / KIMI_MODEL
    - DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL
    - LLM_PRIMARY（可选，默认 kimi）
    - LLM_FALLBACK（可选，默认 deepseek）
    """
    primary_name = os.environ.get("LLM_PRIMARY", "kimi").lower()
    fallback_name = os.environ.get("LLM_FALLBACK", "deepseek").lower()

    if primary_name == "kimi":
        primary = ProviderConfig.kimi()
        fallback = ProviderConfig.deepseek()
    else:
        primary = ProviderConfig.deepseek()
        fallback = ProviderConfig.kimi()

    return LLMBridge(
        primary=primary,
        fallback=fallback,
        spirit_layer=spirit_layer,
        auto_test=auto_test
    )


# =============================================================================
# 测试
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("LLM 桥接层 v1.0 测试")
    print("=" * 60)

    # 创建桥接层（会自动测试连接）
    bridge = create_default_bridge(auto_test=True)

    print(f"\n{'─' * 60}")
    print("自我诊断：")
    diag = bridge.diagnose()
    for k, v in diag.to_dict().items():
        print(f"  {k}: {v}")

    print(f"\n{'─' * 60}")
    print("信任报告：")
    report = bridge.get_trust_report()
    for provider, metrics in report.items():
        print(f"  {provider}: {json.dumps(metrics, ensure_ascii=False)}")

    print(f"\n{'=' * 60}")
    print("测试完成")
    print(f"{'=' * 60}")
