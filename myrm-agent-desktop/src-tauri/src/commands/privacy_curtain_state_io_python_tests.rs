//! 状态文件读取与另一进程替换的跨进程测试：写者是真实的 Python 进程，对应生产里 server 的
//! `os.replace`（`curtain_bridge._write_pending_flag`）。壳自己的改名只是另一种写者，
//! 同进程的并发读写测试在 `privacy_curtain_state_io.rs`。
//!
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
