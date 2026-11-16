//! 状态文件与 server 进程之间的跨进程测试，两个方向各用真实的 Python 进程做对端：
//! - 壳读、Python 写：对应 server 的 `os.replace`（`curtain_bridge._write_pending_flag`）；
//! - 壳写、Python 读：对应 server 读状态的 `read_curtain_state`（先 `is_file` 再 `json.loads`）。
//!
//! 壳自己读写同一文件的并发测试在 `privacy_curtain_state_io.rs`。
//! 本机没有 Python 时跳过；CI 上没有则失败，免得这项测量悄悄不再执行。

use std::collections::BTreeMap;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use super::privacy_curtain_state_io::{read_document, replace_document, Document, IO_RETRY_PAUSE};

/// 读者见过这么多份不同的文档，才算与写者真正交错过。
const DISTINCT_DOCUMENTS: u32 = 1_000;

/// server 写租约位的两步：写临时文件，再 `os.replace` 到目标，循环到停止文件出现。
/// 目标恰被读者占着而替换被拒（Windows 的 PermissionError）时重试；结束时打印「替换轮数 被拒次数」。
const PYTHON_WRITER: &str = r#"
import os
import sys
import time

path, stop = sys.argv[1], sys.argv[2]
temp = path + ".py.tmp"
rounds = refused = 0
while not os.path.exists(stop):
    rounds += 1
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write('{"round":%d,"padding":"%s"}' % (rounds, "x" * 256))
    attempts = 0
    while True:
        try:
            os.replace(temp, path)
            break
        except PermissionError:
            attempts += 1
            if attempts > 2000:
                sys.exit("os.replace kept being refused")
            time.sleep(0.001)
    refused += attempts
print(rounds, refused)
"#;

/// server 读状态的方式（`read_curtain_state`）：先 `is_file`，再 `json.loads(read_text())`。
/// 循环读到见过足够多份不同的文档、停止文件出现或超时；结束时用一行 JSON 报告读了多少次、
/// 见过多少份不同文档、撕裂 / 不存在的次数，以及 OSError 按种类的计数。
const PYTHON_READER: &str = r#"
import json
import os
import sys
import time

path, stop, wanted = sys.argv[1], sys.argv[2], int(sys.argv[3])
reads = torn = missing = 0
errors = {}
seen = set()
deadline = time.monotonic() + 60
while len(seen) < wanted and not os.path.exists(stop) and time.monotonic() < deadline:
    reads += 1
    try:
        if not os.path.isfile(path):
            missing += 1
        else:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            try:
                seen.add(json.loads(text)["round"])
            except (ValueError, KeyError):
                torn += 1
    except OSError as error:
        kind = type(error).__name__
        errors[kind] = errors.get(kind, 0) + 1
    time.sleep(0.0001)
print(json.dumps({"reads": reads, "distinct": len(seen), "torn": torn, "missing": missing, "errors": errors}))
"#;

/// 能运行脚本的 Python 解释器。本机没有就无从测量；CI 上找不到说明环境变了，必须失败。
fn find_python() -> Option<&'static str> {
    let candidates: &[&str] = if cfg!(windows) {
        &["python", "py"]
    } else {
        &["python3", "python"]
    };
    let found = candidates.iter().copied().find(|name| {
        Command::new(name)
            .arg("--version")
            .output()
            .is_ok_and(|output| output.status.success())
    });
    assert!(
        found.is_some() || std::env::var_os("CI").is_none(),
        "no Python interpreter on this CI runner (tried {candidates:?})"
    );
    found
}

/// 读者一路读下来的账。
#[derive(Default)]
struct Tally {
    reads: u32,
    /// 读到了但不是完整文档。
    torn: u32,
    /// 被判为「不存在 / 无效」。
    empty: u32,
    /// 重试预算耗尽仍读不出来。
    unreadable: u32,
    /// 读取遇到过的每个错误按种类计数（瞬时错误已被重试吸收，只在这里留痕）。
    errors_by_kind: BTreeMap<String, u32>,
}

/// 文档里的轮次号；不是完整的 JSON 文档（被撕裂）就是 None。
fn round_of(text: &str) -> Option<u64> {
    serde_json::from_str::<serde_json::Value>(text)
        .ok()?
        .get("round")?
        .as_u64()
}

/// 按生产的读取与重试预算反复读 `path`，直到 `done`；每读到一份与上次不同的文档就给 `distinct` 加一。
fn read_until_done(path: &std::path::Path, done: &AtomicBool, distinct: &AtomicU32) -> Tally {
    let mut tally = Tally::default();
    let mut last_round = 0;
    while !done.load(Ordering::Relaxed) {
        let document = read_document(
            || {
                let read = std::fs::read_to_string(path);
                if let Err(error) = &read {
                    let kind = format!("{:?}", error.kind());
                    *tally.errors_by_kind.entry(kind).or_default() += 1;
                }
                read
            },
            IO_RETRY_PAUSE,
        );
        tally.reads += 1;
        match document {
            Document::Text(text) => match round_of(&text) {
                Some(round) if round != last_round => {
                    last_round = round;
                    distinct.fetch_add(1, Ordering::Relaxed);
                }
                Some(_) => {}
                None => tally.torn += 1,
            },
            Document::Empty => tally.empty += 1,
            Document::Unreadable => tally.unreadable += 1,
        }
        // 读得比 server 勤，但不是一刻不停：句柄几乎一直开着会让写者很难换进去，生产里不是这样。
        thread::sleep(Duration::from_micros(100));
    }
    tally
}

/// 生产里会撞上的写者是 server 的 Python `os.replace`：让真实的 Python 进程持续替换同一个文件，
/// 读者读到的必须是完整文档，替换期间不得被看成「不存在 / 无效」，也不得在预算内读不出来；
/// 读取遇到的错误按种类计数后打印，作为这个平台上的实测（CI 日志里可查）。
#[test]
fn a_reader_survives_a_python_process_replacing_the_file() {
    let Some(python) = find_python() else {
        eprintln!("skipped: no Python interpreter on this machine");
        return;
    };
    let dir = tempfile::tempdir().expect("tempdir");
    let (path, stop, script) = (
        dir.path().join("curtain_state.json"),
        dir.path().join("stop"),
        dir.path().join("writer.py"),
    );
    assert!(replace_document(&path, r#"{"round":0}"#, IO_RETRY_PAUSE));
    std::fs::write(&script, PYTHON_WRITER).expect("write the script");

    let distinct = Arc::new(AtomicU32::new(0));
    let done = Arc::new(AtomicBool::new(false));
    let reader = {
        let (distinct, done, path) = (Arc::clone(&distinct), Arc::clone(&done), path.clone());
        thread::spawn(move || read_until_done(&path, &done, &distinct))
    };

    let mut writer = Command::new(python)
        .arg(&script)
        .arg(&path)
        .arg(&stop)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn the writer");
    let deadline = Instant::now() + Duration::from_secs(60);
    while distinct.load(Ordering::Relaxed) < DISTINCT_DOCUMENTS
        && Instant::now() < deadline
        && writer.try_wait().expect("poll the writer").is_none()
    {
        thread::sleep(Duration::from_millis(5));
    }
    std::fs::write(&stop, "").expect("stop file");
    let output = writer.wait_with_output().expect("writer output");
    done.store(true, Ordering::Relaxed);
    let tally = reader.join().expect("reader");

    println!(
        "python writer vs shell reader: writer reports `{}` (replaces, refused attempts); \
         {} reads saw {} distinct documents; errors seen by kind: {:?}",
        String::from_utf8_lossy(&output.stdout).trim(),
        tally.reads,
        distinct.load(Ordering::Relaxed),
        tally.errors_by_kind,
    );
    assert!(
        output.status.success(),
        "the writer failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(
        distinct.load(Ordering::Relaxed) >= DISTINCT_DOCUMENTS,
        "the reader never overlapped the writer enough to measure anything"
    );
    assert_eq!(tally.torn, 0, "reader saw a torn document");
    assert_eq!(
        tally.empty, 0,
        "reader saw the file as missing or invalid while it was being replaced"
    );
    assert_eq!(
        tally.unreadable, 0,
        "reader could not read the file within the retry budget"
    );
}

/// `PYTHON_READER` 打印的账。
#[derive(serde::Deserialize)]
struct ReaderReport {
    reads: u64,
    distinct: u32,
    torn: u32,
    missing: u32,
    errors: BTreeMap<String, u32>,
}

/// 第 `round` 轮写入的文档（带填充，让一次写入不是单个磁盘块的原子写）。
fn document(round: u32) -> String {
    serde_json::json!({ "round": round, "padding": "x".repeat(256) }).to_string()
}

/// 壳是写者的方向：壳用生产的 `replace_document` 持续替换状态文件，真实的 Python 进程按 server 的
/// 读法持续读。读者读到的必须是完整文档，替换期间不得看到「不存在」或读取出错；壳的每次写入都要落盘。
/// 读者的账打印出来，作为这个平台上的实测（CI 日志里可查）。
#[test]
fn a_python_reader_survives_the_shell_replacing_the_file() {
    let Some(python) = find_python() else {
        eprintln!("skipped: no Python interpreter on this machine");
        return;
    };
    let dir = tempfile::tempdir().expect("tempdir");
    let (path, stop, script) = (
        dir.path().join("curtain_state.json"),
        dir.path().join("stop"),
        dir.path().join("reader.py"),
    );
    assert!(replace_document(&path, &document(0), IO_RETRY_PAUSE));
    std::fs::write(&script, PYTHON_READER).expect("write the script");

    let mut reader = Command::new(python)
        .arg(&script)
        .arg(&path)
        .arg(&stop)
        .arg(DISTINCT_DOCUMENTS.to_string())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn the reader");
    let deadline = Instant::now() + Duration::from_secs(60);
    let (mut round, mut failed_writes) = (0_u32, 0_u32);
    while reader.try_wait().expect("poll the reader").is_none() && Instant::now() < deadline {
        round += 1;
        if !replace_document(&path, &document(round), IO_RETRY_PAUSE) {
            failed_writes += 1;
        }
    }
    std::fs::write(&stop, "").expect("stop file");
    let output = reader.wait_with_output().expect("reader output");
    assert!(
        output.status.success(),
        "the reader failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let report: ReaderReport = serde_json::from_slice(&output.stdout).expect("the reader's report");

    println!(
        "shell writer vs python reader: {round} replaces ({failed_writes} not recorded); \
         python reader: {} reads saw {} distinct documents, {} torn, {} missing, errors by kind: {:?}",
        report.reads, report.distinct, report.torn, report.missing, report.errors,
    );
    assert!(
        report.distinct >= DISTINCT_DOCUMENTS,
        "the reader never overlapped the writer enough to measure anything"
    );
    assert_eq!(report.torn, 0, "reader saw a torn document");
    assert_eq!(
        report.missing, 0,
        "reader saw the file as missing while it was being replaced"
    );
    assert!(
        report.errors.is_empty(),
        "reader could not read the file: {:?}",
        report.errors
    );
    assert_eq!(
        failed_writes, 0,
        "the shell could not record a state within its retry budget"
    );
}
