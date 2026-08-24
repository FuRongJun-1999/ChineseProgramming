"""
compiler_core · 编译器核心
"""
from .lexer import Lexer, Token, TokenType
from .parser import Parser, ASTNode
from .name_checker import NameChecker
from .codegen import CodeGenerator
from .api import compile_source, CompileOptions, CompileResult
from .llm_bridge import (
    LLMBridge, create_default_bridge,
    LLMProvider, ProviderConfig,
    LLMCallRecord, LLMTrustMetrics,
    SpiritLayerProxy, NullSpiritLayer,
    DiagnosticReport,
)
from .trust_engine import (
    TrustEngine, TrustState, TrustConfig,
    create_trust_engine,
)
from .info_gap_engine import (
    InfoGapEngine, InfoGapState, InfoGapConfig,
    create_info_gap_engine,
)
from .protocol_prompt import (
    build_system_prompt, get_context_for_task,
    CORE_PROMPT,
)

__all__ = [
    "Lexer", "Token", "TokenType",
    "Parser", "ASTNode",
    "NameChecker",
    "CodeGenerator",
    "compile_source", "CompileOptions", "CompileResult",
    "LLMBridge", "create_default_bridge",
    "LLMProvider", "ProviderConfig",
    "LLMCallRecord", "LLMTrustMetrics",
    "SpiritLayerProxy", "NullSpiritLayer",
    "DiagnosticReport",
    "TrustEngine", "TrustState", "TrustConfig",
    "create_trust_engine",
    "InfoGapEngine", "InfoGapState", "InfoGapConfig",
    "create_info_gap_engine",
    "build_system_prompt", "get_context_for_task",
    "CORE_PROMPT",
]
