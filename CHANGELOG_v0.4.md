# Protocol Compiler v0.4 · 更新日志

**日期**：2026-09-06
**版本**：v0.4.0（Rust 原生后端 · VM 路线）

---

## 荣裁定（2026-09-06 访谈四条）

1. **架构：VM 路线**——AST → 智能论字节码 → Rust。Rust 侧是 `.pbc` 的独立解释器（与 C3「零 Python 运行时依赖」定位一致），非 AST→Rust 源码直译。
2. **产物形态**：cargo 项目 + 运行时库。
3. **验收标准**：双后端语义等价（同一 .pbc，Python VM vs Rust VM 终态一致）+ cargo build/clippy 零警告 + 既有测试基线不破坏。
4. **源语言范围**：现有子集直译（顺序/条件/循环/函数/赋值/比较/算术），不扩语法。

## 新增

### `core/rust_codegen.py` ✅

- `generate_rust_project(source, out_dir)`：中文源码 → cargo 项目（program.pbc 编译期嵌入 `include_bytes!`）
- `build_and_run(project_dir, symbols, trust)`：cargo build --release + 运行 → 终态 JSON（与 Python `run_pbc` 同构）
- `compile_source_to_rust(source, out_dir)`：一步到位（生成→构建→运行）

### `rust_runtime/`（Rust VM 模板，纯 std 零依赖）✅

- `src/pbc.rs`：.pbc 反序列化（op 名 + arg tag 0-6，与 Python 侧格式逐字节对齐）
- `src/vm.rs`：VM 解释器——ip+值栈+符号表（以名举实）+条件空间栈+信任寄存器+调用栈帧；
  止(ZHI)/无为(WUWEI) 为语言语义非错误；步数上限防死循环；Int/Float 保留整数算术语义
  （DIV 恒真除，对齐 Python）；Bool 数值化对齐 `False == 0`；truthy 严格对齐 VM 语义
  （仅 None/False/0 为假，空字符串为真）
- `src/main.rs`：执行入口，`--trust`/`--symbols` 注入初始环境，终态 JSON 手写序列化（零 crate 依赖）

### `.pbc 格式 v0.4 扩展（向后兼容）✅

- **tag6** = `(i64 入口 ip + str列表 参数名)`——CALL 签名序列化。此前 tag5 仅 `(f64,i64)`，
  含函数定义的字节码无法落盘（既有 C3 缺口）；旧 tag 0-5 语义不变，旧 .pbc 文件照常可读。
- CLI 新增 `rust` 子命令：`python -m cli rust src.proto -o out/dir --set 名=值 --trust 0.5 [--no-run]`

## 验收记录（2026-09-06，`tests/test_rust_codegen.py` 13/13）

| 用例 | Python VM | Rust VM | 等价 |
|------|-----------|---------|------|
| trust 样例（道/德/若/止） | trust=0.8, halt | trust=0.8, halt | ✓ |
| 循环（当…执行 计数 0→3） | 计数=3, trust=0.6 | 计数=3, trust=0.6 | ✓ |
| 递归阶乘 4!（CALL tag6 路径） | 结果=24 | 结果=24 | ✓ |
| 多函数互调（双倍/计算） | 结果=11 | 结果=11 | ✓ |
| tag6 往返 / 旧格式兼容 / clippy 零警告 / 既有 VM 基线 | — | — | ✓ |

全量既有回归：full_pipeline / new_modules / condition_vm 13 / pbc 5 / compiler_c2 12 /
c4_tooling 8 / func_compile 10 / loop_compile 11 —— 全部通过，零破坏。

## 已声明局限

- Python 无限精度整数不模拟（i64 溢出降级 Float）
- 字符串不参与算术；跨类型比较（str vs 数值）报错（对齐 Python3 TypeError 语义）
- trust 序列化舍入：Rust `format!("{}", 2.0)` 输出 `2`（Python json 为 `2.0`）——
  等价对照用数值容差，不比字符串表示
