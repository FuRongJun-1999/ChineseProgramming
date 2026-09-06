//! swarm.rs · 蜂群协调器（多进程蜂群 · 对齐 aeis.swarm 语义）
//! 荣 2026-09-06 裁定：多实例并行（进程级）+ 消息传递 + 实例私有信任/条件空间 + 聚合层。
//!   - 实例 = protocol_vm --serve 子进程（进程隔离，stdio 管道通信）
//!   - 事件总线：WAL 落盘（events.jsonl）+ HMAC-SHA256 签名 + ACK 追踪
//!   - 消息传递语义：事件投递 = 写入目标实例下一轮的「收件箱」初始符号
//!   - 信任聚合：T_avg/T_min/T_variance/T_alignment（对齐 trust_aggregator.py，
//!     防操纵：同轮同实例去重 B6 / 0-1 夹取 / verified 过滤）
//!
//! 纯 std 零 crate 依赖（SHA256/HMAC 手写见 hmac.rs）。

use std::collections::{HashMap, HashSet};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::process::{Child, Command, Stdio};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::hmac::{hmac_sha256, hex32};

/// 延迟分级（对齐 event_bus.py DELIVERY-V1）——V0 仅作 WAL 元数据标记，
/// 投递间隔调度为后续版本（荣小步实验纪律：先同步路由）
#[allow(dead_code)]
pub const DELAY_HIGH_MS: u64 = 500;
#[allow(dead_code)]
pub const DELAY_MID_MS: u64 = 5_000;
#[allow(dead_code)]
pub const DELAY_LOW_MS: u64 = 30_000;

#[derive(Debug, Clone)]
pub struct InstanceSpec {
    pub id: String,
    /// V0 仅随报告透出（身份语义声明），协调器路由暂不消费
    #[allow(dead_code)]
    pub role: String,
    /// 初始信任值
    pub trust: f64,
    /// 初始符号表（JSON 对象文本，由 Python 侧生成）
    pub symbols_json: String,
}

#[derive(Debug, Clone)]
pub struct Event {
    pub ts: u64,
    pub from_id: String,
    pub to_id: String,
    pub event_type: String,
    pub payload_json: String,
    pub round_no: u64,
    pub level: u8, // 0=高 1=中 2=低
    pub hmac_hex: String,
}

pub struct SwarmConfig {
    pub shared_secret: String,
    pub instances: Vec<InstanceSpec>,
    /// 路由表：(round, from, event_type) → [(to, payload_json, level)]
    /// 第一版语义：实例 r 轮终态后，按路由表把指定符号载荷广播给目标实例 r+1 轮。
    /// payload_json 里可用 "@trust" 占位（运行时替换为源实例终态信任值）。
    pub routes: Vec<Route>,
}

#[derive(Debug, Clone)]
pub struct Route {
    pub from_id: String,
    pub event_type: String,
    pub to_id: String,
    pub payload_json: String,
    pub level: u8,
}

pub struct SwarmReport {
    pub rounds: u64,
    pub events: Vec<Event>,
    pub acks: HashSet<String>, // event hex 索引 → 已 ACK
    pub t_avg: f64,
    pub t_min: f64,
    pub t_variance: f64,
    pub t_alignment: f64,
    pub final_states: HashMap<String, serde_json_like::Value>,
}

/// 极简 JSON（与 serve.rs serde_like 同源实现——单文件内聚）
pub mod serde_json_like {
    use std::collections::HashMap;

    #[derive(Debug, Clone)]
    pub enum Value {
        Null,
        Bool(bool),
        Num(f64),
        Str(String),
        List(Vec<Value>),
        Obj(HashMap<String, Value>),
    }

    impl Value {
        pub fn get(&self, k: &str) -> Option<&Value> {
            match self {
                Value::Obj(m) => m.get(k),
                _ => None,
            }
        }
        pub fn as_f64(&self) -> Option<f64> {
            match self {
                Value::Num(f) => Some(*f),
                _ => None,
            }
        }
        pub fn as_str(&self) -> Option<&str> {
            match self {
                Value::Str(s) => Some(s),
                _ => None,
            }
        }
    }

    pub fn stringify(v: &Value) -> String {
        match v {
            Value::Null => "null".into(),
            Value::Bool(b) => b.to_string(),
            Value::Num(f) => format!("{f}"),
            Value::Str(s) => format!("\"{}\"", escape(s)),
            Value::List(items) => {
                let parts: Vec<String> = items.iter().map(stringify).collect();
                format!("[{}]", parts.join(","))
            }
            Value::Obj(m) => {
                let mut keys: Vec<&String> = m.keys().collect();
                keys.sort();
                let parts: Vec<String> = keys
                    .iter()
                    .map(|k| format!("\"{}\":{}", escape(k), stringify(&m[*k])))
                    .collect();
                format!("{{{}}}", parts.join(","))
            }
        }
    }

    pub fn escape(s: &str) -> String {
        let mut out = String::new();
        for c in s.chars() {
            match c {
                '"' => out.push_str("\\\""),
                '\\' => out.push_str("\\\\"),
                '\n' => out.push_str("\\n"),
                '\r' => out.push_str("\\r"),
                c if (c as u32) < 0x20 => {
                    out.push_str(&format!("\\u{:04x}", c as u32));
                }
                c => out.push(c),
            }
        }
        out
    }

    pub fn parse(s: &str) -> Result<Value, String> {
        let b: Vec<char> = s.chars().collect();
        let mut i = 0usize;
        let v = pv(&b, &mut i)?;
        Ok(v)
    }

    fn skip_ws(b: &[char], i: &mut usize) {
        while *i < b.len() && b[*i].is_whitespace() {
            *i += 1;
        }
    }

    fn pv(b: &[char], i: &mut usize) -> Result<Value, String> {
        skip_ws(b, i);
        match b.get(*i) {
            Some('{') => {
                *i += 1;
                let mut m = HashMap::new();
                loop {
                    skip_ws(b, i);
                    match b.get(*i) {
                        Some('}') => {
                            *i += 1;
                            return Ok(Value::Obj(m));
                        }
                        Some(',') => {
                            *i += 1;
                        }
                        Some('"') => {
                            let (k, ni) = ps(b, *i)?;
                            *i = ni;
                            skip_ws(b, i);
                            if b.get(*i) != Some(&':') {
                                return Err("缺 ':'".into());
                            }
                            *i += 1;
                            let v = pv(b, i)?;
                            m.insert(k, v);
                        }
                        _ => return Err("对象非法".into()),
                    }
                }
            }
            Some('[') => {
                *i += 1;
                let mut items = Vec::new();
                loop {
                    skip_ws(b, i);
                    match b.get(*i) {
                        Some(']') => {
                            *i += 1;
                            return Ok(Value::List(items));
                        }
                        Some(',') => {
                            *i += 1;
                        }
                        _ => items.push(pv(b, i)?),
                    }
                }
            }
            Some('"') => {
                let (s, ni) = ps(b, *i)?;
                *i = ni;
                Ok(Value::Str(s))
            }
            Some(_) => {
                let start = *i;
                while *i < b.len()
                    && !b[*i].is_whitespace()
                    && !matches!(b[*i], ',' | '}' | ']')
                {
                    *i += 1;
                }
                let raw: String = b[start..*i].iter().collect();
                Ok(match raw.as_str() {
                    "true" => Value::Bool(true),
                    "false" => Value::Bool(false),
                    "null" => Value::Null,
                    _ => Value::Num(
                        raw.parse::<f64>()
                            .map_err(|_| format!("非法数值 {raw}"))?,
                    ),
                })
            }
            None => Err("JSON 意外结束".into()),
        }
    }

    fn ps(b: &[char], start: usize) -> Result<(String, usize), String> {
        let mut out = String::new();
        let mut i = start + 1;
        while i < b.len() {
            match b[i] {
                '"' => return Ok((out, i + 1)),
                '\\' => {
                    i += 1;
                    match b.get(i) {
                        Some('"') => out.push('"'),
                        Some('\\') => out.push('\\'),
                        Some('n') => out.push('\n'),
                        Some('t') => out.push('\t'),
                        _ => return Err("不支持的转义".into()),
                    }
                }
                c => out.push(c),
            }
            i += 1;
        }
        Err("字符串未闭合".into())
    }
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

fn sign_event(key: &str, ev: &Event) -> String {
    // 签名串与 Python 侧 event_bus 约定一致：type|from|to|round|ts|payload
    let msg = format!(
        "{}|{}|{}|{}|{}|{}",
        ev.event_type, ev.from_id, ev.to_id, ev.round_no, ev.ts, ev.payload_json
    );
    hex32(&hmac_sha256(key.as_bytes(), msg.as_bytes()))
}

struct InstanceProc {
    spec: InstanceSpec,
    child: Child,
    stdin: BufWriter<std::process::ChildStdin>,
}

impl InstanceProc {
    fn spawn(exe: &str, spec: &InstanceSpec) -> Result<Self, String> {
        let mut child = Command::new(exe)
            .arg("--serve")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("启动实例 {} 失败: {e}", spec.id))?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "无法获取实例 stdin".to_string())?;
        Ok(InstanceProc {
            spec: spec.clone(),
            child,
            stdin: BufWriter::new(stdin),
        })
    }

    /// 执行一轮：请求 = 初始环境（symbols/trust/condition_space）+ 收件箱
    fn run_round(
        &mut self,
        round_no: u64,
        inbox: &HashMap<String, String>,
    ) -> Result<serde_json_like::Value, String> {
        let mut symbols_parts: Vec<String> = Vec::new();
        // 每轮都带初始符号（VM 符号表不跨轮持久——每轮是完整环境；
        // 跨轮传递的数据只能走消息，这正是消息传递模型的语义）
        if !self.spec.symbols_json.is_empty() {
            symbols_parts.push(format!("\"初始符号\":{}", self.spec.symbols_json));
        }
        if !inbox.is_empty() {
            let msgs: Vec<String> = {
                let mut keys: Vec<&String> = inbox.keys().collect();
                keys.sort();
                keys.iter()
                    .map(|k| {
                        format!("{{\"from\":\"{}\",\"payload\":{}}}", k, inbox[*k])
                    })
                    .collect()
            };
            symbols_parts
                .push(format!("\"收件箱\":[{}]", msgs.join(",")));
            symbols_parts.push(format!("\"已收消息数\":{}", inbox.len()));
        }
        let req = format!(
            "{{\"symbols\":{{{}}},\"trust\":{},\"round_no\":{}}}\n",
            symbols_parts.join(","),
            self.spec.trust,
            round_no
        );
        self.stdin
            .write_all(req.as_bytes())
            .map_err(|e| format!("实例 {} 管道断裂: {e}", self.spec.id))?;
        self.stdin
            .flush()
            .map_err(|e| format!("实例 {} flush 失败: {e}", self.spec.id))?;
        let stdout = self
            .child
            .stdout
            .as_mut()
            .ok_or_else(|| "无法读取实例 stdout".to_string())?;
        let mut reader = BufReader::new(stdout);
        let mut line = String::new();
        reader
            .read_line(&mut line)
            .map_err(|e| format!("实例 {} 读取失败: {e}", self.spec.id))?;
        serde_json_like::parse(line.trim())
            .map_err(|e| format!("实例 {} 终态非法: {e}", self.spec.id))
    }
}

impl Drop for InstanceProc {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

/// 蜂群执行：rounds 轮，每轮各实例执行一次；路由表决定跨实例消息
pub fn run_swarm(exe: &str, cfg: &SwarmConfig, rounds: u64, wal_path: &str) -> Result<SwarmReport, String> {
    let mut procs: Vec<InstanceProc> = Vec::new();
    for spec in &cfg.instances {
        procs.push(InstanceProc::spawn(exe, spec)?);
    }
    let mut wal = std::fs::File::create(wal_path)
        .map_err(|e| format!("WAL 创建失败: {e}"))?;
    let mut all_events: Vec<Event> = Vec::new();
    let mut acks: HashSet<String> = HashSet::new();
    // 收件箱：round → to_id → {from_id: payload_json}
    let mut inboxes: HashMap<u64, HashMap<String, HashMap<String, String>>> =
        HashMap::new();
    let mut last_states: HashMap<String, serde_json_like::Value> = HashMap::new();
    let mut last_trust: HashMap<String, f64> = HashMap::new();

    for round in 1..=rounds {
        // 本轮各实例收到的消息（上一轮路由产出）
        let round_inboxes = inboxes.remove(&round).unwrap_or_default();
        let mut new_events: Vec<Event> = Vec::new();
        for p in procs.iter_mut() {
            let inbox = round_inboxes.get(&p.spec.id).cloned().unwrap_or_default();
            let st = p.run_round(round, &inbox)?;
            last_states.insert(p.spec.id.clone(), st.clone());
            // 信任提交（防操纵：0-1 夹取；同轮同实例由聚合器去重）。
            // error 终态无 trust 字段 → 沿用上一轮值（实例故障不推平信任曲线）
            let prev_t = last_trust
                .get(&p.spec.id)
                .cloned()
                .unwrap_or(p.spec.trust.clamp(0.0, 1.0));
            let t = st
                .get("trust")
                .and_then(|x| x.as_f64())
                .unwrap_or(prev_t)
                .clamp(0.0, 1.0);
            last_trust.insert(p.spec.id.clone(), t);
            // ACK 事件：实例收到收件箱 → 回执
            if !inbox.is_empty() {
                let ev = Event {
                    ts: now_ms(),
                    from_id: p.spec.id.clone(),
                    to_id: "协调器".into(),
                    event_type: "ACK".into(),
                    payload_json: format!("{{\"round\":{}}}", round),
                    round_no: round,
                    level: 0,
                    hmac_hex: String::new(),
                };
                let mut ev = ev;
                ev.hmac_hex = sign_event(&cfg.shared_secret, &ev);
                acks.insert(ev.hmac_hex.clone());
                new_events.push(ev);
            }
            // 路由产出：from=p.spec.id 的路由 → 目标实例下一轮收件箱
            for r in &cfg.routes {
                if r.from_id == p.spec.id {
                    let payload = r.payload_json.replace("@trust", &format!("{t}"));
                    let ev = Event {
                        ts: now_ms(),
                        from_id: p.spec.id.clone(),
                        to_id: r.to_id.clone(),
                        event_type: r.event_type.clone(),
                        payload_json: payload.clone(),
                        round_no: round,
                        level: r.level,
                        hmac_hex: String::new(),
                    };
                    let mut ev = ev;
                    ev.hmac_hex = sign_event(&cfg.shared_secret, &ev);
                    let slot = inboxes
                        .entry(round + 1)
                        .or_default()
                        .entry(r.to_id.clone())
                        .or_default();
                    slot.insert(p.spec.id.clone(), payload);
                    new_events.push(ev);
                }
            }
        }
        // WAL 落盘（append-only）
        for ev in &new_events {
            let line = format!(
                "{{\"ts\":{},\"from\":\"{}\",\"to\":\"{}\",\"type\":\"{}\",\"round\":{},\"level\":{},\"hmac\":\"{}\",\"payload\":{}}}\n",
                ev.ts,
                serde_json_like::escape(&ev.from_id),
                serde_json_like::escape(&ev.to_id),
                serde_json_like::escape(&ev.event_type),
                ev.round_no,
                ev.level,
                ev.hmac_hex,
                ev.payload_json
            );
            wal.write_all(line.as_bytes())
                .map_err(|e| format!("WAL 写入失败: {e}"))?;
        }
        all_events.extend(new_events);
    }
    // 实例退场
    drop(procs);
    // 信任聚合（对齐 trust_aggregator.snapshot：每实例最后轮 trust）
    let mut ts: Vec<f64> = Vec::new();
    for spec in &cfg.instances {
        if let Some(st) = last_states.get(&spec.id) {
            if let Some(t) = st.get("trust").and_then(|x| x.as_f64()) {
                ts.push(t.clamp(0.0, 1.0));
            }
        }
    }
    let n = ts.len() as f64;
    let t_avg = if n > 0.0 { ts.iter().sum::<f64>() / n } else { 0.0 };
    let t_min = if ts.is_empty() {
        0.0
    } else {
        ts.iter().cloned().fold(f64::INFINITY, f64::min)
    };
    let t_variance = if n > 0.0 {
        ts.iter().map(|t| (t - t_avg) * (t - t_avg)).sum::<f64>() / n
    } else {
        0.0
    };
    let t_alignment = if t_avg > 0.0 {
        1.0 - t_variance / t_avg
    } else {
        0.0
    };
    Ok(SwarmReport {
        rounds,
        events: all_events,
        acks,
        t_avg,
        t_min,
        t_variance,
        t_alignment,
        final_states: last_states,
    })
}

/// 蜂群报告 → JSON（Python 侧消费/对照）
pub fn report_json(rep: &SwarmReport) -> String {
    let mut out = String::from("{");
    out.push_str(&format!("\"rounds\":{}", rep.rounds));
    out.push_str(&format!(
        ",\"instances\":{}",
        rep.final_states.len()
    ));
    out.push_str(",\"trust\":{");
    out.push_str(&format!(
        "\"T_avg\":{:.6},\"T_min\":{:.6},\"T_variance\":{:.6},\"T_alignment\":{:.6}",
        rep.t_avg, rep.t_min, rep.t_variance, rep.t_alignment
    ));
    out.push('}');
    out.push_str(&format!(",\"events\":{}", rep.events.len()));
    out.push_str(&format!(",\"acks\":{}", rep.acks.len()));
    out.push_str(",\"final_states\":{");
    let mut ids: Vec<&String> = rep.final_states.keys().collect();
    ids.sort();
    for (i, id) in ids.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push_str(&format!(
            "\"{}\":{}",
            serde_json_like::escape(id),
            serde_json_like::stringify(&rep.final_states[*id])
        ));
    }
    out.push_str("}}");
    out
}
