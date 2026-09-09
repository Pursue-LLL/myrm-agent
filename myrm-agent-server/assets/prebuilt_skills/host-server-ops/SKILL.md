---
name: host-server-ops
description: >-
  Systematic host and server health diagnostics and operations across Linux, macOS, and Windows.
  Covers CPU, memory, disk, network, systemd/launchd services, process anomalies, and container runtimes.
  Enforces read-only inspection first, OS-aware command adaptation, and safe remediation boundaries.
version: 1.0.0
category: operations
tags:
  - devops
  - host-monitoring
  - system-health
  - server-ops
  - linux
  - macos
  - docker
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool
contract:
  steps:
    - "Phase 1: OS & Environment Detection — identify kernel, distro/OS, virtualization, and execution context"
    - "Phase 2: Core Resource Health — probe CPU load, memory utilization, disk space, and inode consumption"
    - "Phase 3: Process & Service Inspection — check top resource consumers, systemd units or launchd daemons"
    - "Phase 4: Network & Socket Triaging — check listening ports, socket states, connectivity, and DNS resolution"
    - "Phase 5: Container & Runtime Health — inspect Docker/containerd status if installed"
    - "Phase 6: Synthesis & Remediation Guidance — output structured health report with severity and non-destructive action items"
  potential_traps:
    - description: "Assuming systemd/journalctl commands exist on macOS or BSD environments"
      mitigation: "Always probe `uname -s` first; branch to launchctl/vm_stat/top on Darwin and systemctl/free/journalctl on Linux"
      severity: high
    - description: "Running destructive cleanup commands (e.g. `rm -rf`, `docker system prune -a --volumes`) without user confirmation"
      mitigation: "Enforce read-only-first; only suggest cleanup commands as recommended steps with explicit risk warnings"
      severity: critical
    - description: "Attempting to inspect or access private keys in ~/.ssh directly"
      mitigation: "Strict security boundary: never probe or read private key files under ~/.ssh; use SSH host alias configs or authorized endpoints only"
      severity: critical
    - description: "Overlooking containerized or sandbox execution context"
      mitigation: "Verify if running inside a container or sandbox where host resource metrics may reflect host or container limits"
      severity: medium
  verification_steps:
    - step_id: os_identified
      description: "Target operating system, release, and architecture identified"
      validation_method: "uname -s && uname -m or ver/systeminfo captured"
      is_required: true
    - step_id: resource_metrics_gathered
      description: "CPU, memory, disk space metrics parsed"
      validation_method: "Quantitative metrics gathered (load averages, used/free RAM, disk percent)"
      is_required: true
    - step_id: read_only_first_maintained
      description: "No mutating or destructive commands executed during routine health check"
      validation_method: "All executed commands are non-mutating status probes"
      is_required: true
    - step_id: structured_report_delivered
      description: "Delivers clear triage summary with OK/WARN/CRITICAL statuses"
      validation_method: "Structured output contains health grade, resource breakdown, and actionable findings"
      is_required: true
  success_criteria: "Complete, non-destructive host health assessment with quantitative resource metrics, service state analysis, and prioritized findings"
  estimated_duration_seconds: 600
---

# Host Server Operations & Health Diagnostics

Systematic operations workflow for diagnosing host health, resource saturation, failing services, and system anomalies across Linux, macOS, and Windows environments.

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: explaining why this inspection runs) and **`command`**. Put `reason` first.

## Operating Principles

1. **Read-Only First (Zero Collateral Impact)**:
   Diagnostic passes MUST be strictly non-mutating. Never kill processes, wipe caches, restart system services, or delete files without explicit user instruction.
2. **OS & Environment Adaptation**:
   Detect the OS architecture before firing commands. Never assume Linux utilities (`systemctl`, `free -m`, `ip addr`) exist on macOS (`top -l 1`, `vm_stat`, `netstat`, `launchctl`).
3. **Execution Context Awareness**:
   Distinguish between:
   - Local sandbox / container (where `df -h` or `/proc` might show container or virtual mount limitations)
   - Cloud hosted instance (restricted host primitives)
   - Bare metal or virtual machine with root access
4. **Credential & Key Safety**:
   Never access, read, or print private keys (`id_rsa`, `*.pem`, `~/.ssh/*`). Use user-configured SSH profiles or remote wrappers if managing external servers.

---

## Diagnostic Phases

### Phase 1: OS & Platform Identification

Identify operating system, kernel version, uptime, and virtualization context:

```bash
# Unified detection
uname -s -r -m 2>/dev/null || ver
uptime
```

- **Linux**: Check `/etc/os-release` for distribution flavor.
- **macOS (Darwin)**: Use `sw_vers` to determine macOS version.
- **Windows**: Use `systeminfo` or PowerShell `Get-CimInstance Win32_OperatingSystem`.

### Phase 2: Core Resource Saturation

#### 1. CPU & Load Average
- **Linux**: `uptime`, `cat /proc/loadavg`, `top -b -n 1 | head -n 20`
- **macOS**: `top -l 1 -n 10 -s 0 | head -n 25`, `sysctl -n hw.ncpu`
- Evaluate load average against core count. If load > core count * 1.5, mark saturation WARN/CRITICAL.

#### 2. Memory Utilization
- **Linux**: `free -h` or `cat /proc/meminfo`
  - Pay attention to `available` memory, not just `free` (since Linux uses unused RAM for buffer/cache).
- **macOS**: `vm_stat` and calculate active/inactive/wired memory; inspect memory pressure via `memory_pressure` (if available).
- Highlight swap activity (`swapon -s` or `sysctl vm.swapusage`).

#### 3. Storage & Inode Health
- **All POSIX**: `df -h` (check root and key data mount points for >85% capacity).
- **Inodes**: `df -i` (a filesystem can run out of inodes even with free disk space).
- If disk space is critical, isolate largest directories read-only:
  ```bash
  du -sh /* 2>/dev/null | sort -hr | head -n 10
  ```

### Phase 3: Services & Process Anomalies

#### 1. Top Resource Consumers
- Top 5 CPU consumers:
  ```bash
  ps aux --sort=-%cpu 2>/dev/null | head -n 6 || ps aux | head -n 6
  ```
- Top 5 Memory consumers:
  ```bash
  ps aux --sort=-%mem 2>/dev/null | head -n 6 || ps aux | head -n 6
  ```

#### 2. Critical Service States
- **Linux (systemd)**:
  ```bash
  systemctl list-units --state=failed
  ```
- **macOS (launchd)**:
  ```bash
  launchctl list | grep -v "^0" | grep -v "PID"
  ```
- Check system logs for kernel panics, OOM killer triggers, or I/O errors:
  - Linux: `dmesg -T | grep -iE "oom[- ]killer|out of memory|i/o error" | tail -n 20`
  - Linux journal: `journalctl -p 3 -xb --no-pager | tail -n 20`

### Phase 4: Network & Socket Health

1. **Listening Ports**:
   - `ss -tulpn` (Linux) or `netstat -anv | grep LISTEN` (macOS).
2. **Socket States**:
   - Detect excessive `TIME_WAIT` or `CLOSE_WAIT` sockets indicating connection leaks.
3. **Connectivity & DNS**:
   - Check standard outbound resolution: `ping -c 2 1.1.1.1` or `curl -I --connect-timeout 5 https://www.cloudflare.com`.

### Phase 5: Container Runtime Health (If Present)

If Docker or containerd is installed on the host:
```bash
if command -v docker >/dev/null 2>&1; then
    docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Image}}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
fi
```
Check for restarting crash-loops (`Restarting (x)`).

---

## Output Format: Host Health Assessment

Synthesize findings into a concise, professional status report:

```markdown
### 🖥️ Host Health Summary: [HOSTNAME / CONTEXT]
- **Status**: [🟢 HEALTHY | 🟡 ATTENTION NEEDED | 🔴 CRITICAL]
- **OS/Kernel**: [e.g. Linux 6.8.0-ubuntu / Darwin 24.3.0 arm64]
- **Uptime**: [e.g. 14 days, 3 hours]

#### 📊 Core Resource Metrics
| Metric | Current | Threshold / Capacity | Status |
| :--- | :--- | :--- | :--- |
| **CPU Load** | 1.25 / 1.50 / 1.40 | 8 Cores | OK |
| **Memory** | 12.4 GB / 32 GB (38%) | Swap: 0% | OK |
| **Root Disk** | 82 GB / 256 GB (32%) | Inodes: 14% | OK |

#### ⚠️ Issues & Anomalies Detected
- None (or list specific failed services, high-consumption PIDs, or OOM occurrences)

#### 🛠️ Recommended Actions
1. [Action 1: Non-destructive verification or recommended maintenance]
```
