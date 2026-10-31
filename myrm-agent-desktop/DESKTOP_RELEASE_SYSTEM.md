# Desktop 发版与签名系统

> 跨模块技术方案：Tauri 桌面客户端代码签名、公证、OTA 与 CI 验签。  
> 模块入口：[_ARCH.md](_ARCH.md) · [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 发版流程说明

Walkthrough for shipping a signed and notarized MyrmAgent desktop bundle across macOS, Windows, and Linux.

The release workflow at `.github/workflows/desktop-release.yml` consumes every credential below from repository **Secrets** — nothing in this repo holds keys.

Without secrets set, the workflow still produces installers, but they will be unsigned (macOS shows "damaged" warning; Windows triggers SmartScreen). For production releases, **all secrets must be present**.

> **Current state**: only `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` exist as repository secrets (`gh secret list`), so releases take the unsigned path. The Apple / Windows / Linux sections below describe the target setup that applies once those credentials are added.

## Sidecar packaging and verification runs

The Python backend ships as a PyInstaller **one-folder** tree, `binaries/myrmagent-backend/` (`myrmagent-backend[.exe]` + `_internal/`). `tauri.conf.json#bundle.resources` copies it into the bundle and `src-tauri/src/runtime/sidecar_path.rs` is the single place that locates it at runtime. It is a resource, not a Tauri `externalBin`, so the bundler does not sign it.

- **Why a folder**: a one-file build unpacks its whole payload (about 526 MiB) into a temp directory on every launch. A/B on one host, cold start to `/health`: 34.2 s (one-file) vs 12.9 s (one-folder).
- **Linux layout**: the AppImage carries the tree in `usr/share/<product>/binaries/myrmagent-backend` (`tauri.linux.conf.json#bundle.linux.appimage.files`), not in the resource directory `usr/lib/<product>`. linuxdeploy resolves and rewrites every ELF file below `usr/lib`; a PyInstaller tree carries its own libraries, so resolution fails (`Could not find dependency: libswscale-...` on the first release verification run), and forcing it through with `LD_LIBRARY_PATH` rewrote 357 files and added 216 MB of host libraries (including `libssl.so.3`) to the AppDir. `usr/share` is not scanned. `tauri.linux.conf.json` also limits Linux to the AppImage target, because a deb or rpm built from it would ship without a backend.
- **Node.js runtime**: the Next.js standalone server needs a `node`, and a Finder, Start-menu or desktop launch has none on its PATH (macOS gives GUI applications only `/usr/bin:/bin:/usr/sbin:/sbin`), so the shell ships its own and never looks one up on PATH. Before this change, on a hosted macOS runner with that PATH, the backend answered `/health` and the Next server never started (`os error 2`); with a Node.js on PATH both were up within 19 s (run 41133780060). `src-tauri/binaries/myrm-node-<target-triple>[.exe]` is a Tauri `externalBin` (`tauri.conf.json#bundle.externalBin`): the bundler puts it next to the main executable (`Contents/MacOS/` on macOS, the install directory on Windows, `usr/bin/` in the AppImage; measured) and, once Apple credentials exist, signs it with the app (not exercised yet: CI runs without credentials). `src-tauri/src/runtime/node_runtime.rs` resolves it there and fails with a message that names the fetch command when it is missing or empty. `scripts/fetch_node_runtime.py --target <triple>` downloads the official release pinned in `scripts/node_runtime.json` (Node.js 24.22.2, SHA-256 per target) and refuses a file that does not match; every build job runs it before `tauri build`, and `cargo-check.sh` drops `externalBin` from its config override because it compiles and tests, it does not bundle. Cost, measured on hosted runners before and after bundling it: macOS dmg 358.42 to 395.98 MiB and updater tarball 364.09 to 402.79 MiB (about +38 MiB each), Windows NSIS 263.28 to 285.76 MiB and MSI 355.06 to 388.31 MiB, Linux AppImage 482.52 to 521.57 MiB. It does not raise the macOS minimum: the Mach-O header of the Node.js binary declares 13.5, below what several libraries in the sidecar tree declare (up to 15.0).
- **Sidecar working directory**: the backend creates its `.myrm/` state directories in its working directory (the sub-agent checkpoint store does so at import time), so the shell starts it in `<local app data dir>/backend` (`src-tauri/src/runtime/sidecar_path.rs::sidecar_workdir`) and not in the directory the shell itself was started in. That inherited directory is `/` when Finder launches the app, the install directory when a Windows shortcut does, and on Linux the read-only `usr` directory of the mounted image: AppRun changes into it before it starts the shell (`strace` on a hosted runner: `chdir(".../squashfs-root/usr")`). Without an explicit directory the Linux backend exited during import with `PermissionError: '.myrm'` and the shell never reached a healthy backend; the packaged-shell smoke found it (run 41139208095), the earlier script-based smoke started the backend directly and could not. The directory sits under the local, non-roaming app data directory and apart from the user's home directory and workspaces, so the workspace root the backend derives from its working directory is this private directory, not the user's home. In development the shell keeps starting the backend in the server directory.
- **Verification run**: dispatching `desktop-release.yml` on a branch builds every platform package and launches the packaged shell the way a user does (`scripts/ci/desktop-release/smoke_launch_shell.py`, see *Automated CI verification* below): the `.app` plus the extracted updater tarball on macOS, a silent NSIS install on Windows, the extracted AppImage on Linux. The extracted bundles are made read-only first, because a mounted AppImage and a translocated `.app` are, and neither the shell nor the backend may write into its own install directory. Only a `v*` tag push publishes: release creation and asset upload are tag-gated, and a branch run uses the version `0.0.0-<run_number>` (numeric, so the MSI bundler accepts it). The Linux check has one blind spot: the AppImage does not carry `libEGL` (linuxdeploy excludes it), so on a system without Mesa/EGL the shell does not start (measured on a runner without the build dependencies: `libEGL.so.1: cannot open shared object file`, run 41143952302); the build job has it installed, so the smoke passes there.
- **Windows launch conditions**: the Windows sidecar is built `--noconsole` and the shell is a GUI process, so the backend starts with no standard streams (`sys.stdout is None`), and with stdout redirected to a file Python encodes it in the ANSI code page. Either one used to end the backend before its first request (uvicorn's logging setup reads `sys.stdout.isatty()`; the startup banner holds an emoji). `sidecar/stdio_runtime_hook.py` runs first in the frozen app: it supplies null streams and switches the output streams to UTF-8, and the packaged-shell smoke starts the real GUI shell, so the backend runs under the same conditions. Separately, every harness and server module must import on Windows (no `signal.SIGKILL` default argument, no unguarded `import resource`); `tests/architecture/test_windows_import_safety.py` scans for it. Measured on a hosted Windows runner with a fresh profile: `/health` answered after 18.5 s with stdout redirected and after 18.3 s started like the shell starts it.
- **Apple env**: `scripts/ci/desktop-release/export-apple-signing-env.sh` exports the `APPLE_*` variables only when their secrets are non-empty. A variable that is defined but empty makes the Tauri bundler attempt a keychain import and fail.
- **Bundled Node.js under the hardened runtime**: Tauri signs the `externalBin` copy of Node.js with the app identity and `entitlements.plist`, replacing Node's own signature (tauri-bundler `macos/app.rs` puts the copied binaries in the signing list as executables, `macos/sign.rs` passes the configured entitlements to every target). A hardened-runtime Node.js without `com.apple.security.cs.allow-jit` and `allow-unsigned-executable-memory` dies at start-up (`Fatal process out of memory: Failed to reserve virtual memory for CodeRange`, exit status 133; measured on a copy of the pinned darwin-arm64 binary re-signed ad hoc with `--options runtime`: it ran with the project's `entitlements.plist` and crashed without entitlements). The unsigned CI builds never apply the hardened runtime, so `test_desktop_node_runtime.py` pins both keys; after the first signed build, `codesign -d --entitlements - <app>/Contents/MacOS/myrm-node` must list them.
- **Developer ID signing of the sidecar tree (required before Apple credentials are added)**: Apple notarization inspects every Mach-O inside the app, and Tauri does not sign `bundle.resources` entries. Sign the entry executable and every `.so` / `.dylib` under `_internal/` (hardened runtime, secure timestamp) before `tauri build`.
- **Runner images** are pinned to a concrete release (`macos-15`, `ubuntu-22.04`, `ubuntu-24.04`; Windows follows `windows-latest`), never `macos-latest`, so the OS does not change under a release build. GitHub retires a macOS image about a year after its successor ships and fails every job on it during scheduled brownouts first (`macos-14` was retired on 2026-11-02): bump the label when the retirement notice appears. The macOS labels in `harness-test.yml` and `.github/core-platform-matrix.json` follow the same rule.
- **macOS ships for Apple Silicon only.** PyInstaller cannot cross-compile, so an Intel app needs a sidecar frozen on a native Intel host (`macos-15-intel`), and there `uv sync --frozen` stops before the sidecar is built: `onnxruntime 1.26.0` (via `faster-whisper` and the harness `pdf-ocr` extra) ships wheels for macOS arm64 only and has no sdist (measured on a hosted `macos-15-intel` runner), and `cryptography 50.0.0` / `indexed-zstd 1.7.2` would have to compile from their sdists (`myrm-agent-server/uv.lock` lists no macOS x86_64 wheel for them). The Intel installer published up to `v0.1.39` never worked: it was built on an arm64 runner, so its `MyrmAgent_x64.app.tar.gz` holds an x86_64 shell and `agent-runner` around an arm64 `myrmagent-backend` (measured on the published tarball), and an arm64 executable cannot run on an Intel Mac. The pipeline therefore has no Intel job, `latest.json` carries no `darwin-x86_64` entry, and `pick-platform-asset.sh` never selects an Intel bundle from an older release. `sidecar/build.py` asserts the sidecar's architecture (`lipo -archs`) and `test_desktop_release_inputs.py` pins each build job to a runner of the architecture it bundles, so a mismatched bundle cannot be produced again. Supporting Intel again takes a native Intel runner, a dependency set that installs there (replace `onnxruntime`, or keep the extras that need it out of the Intel lock), and a new `build-macos-x64` job with its `darwin-x86_64` manifest key and installer glob.

---

## Quick Reference — Required Repository Secrets

| Secret | Platform | What it is |
|---|---|---|
| `TAURI_SIGNING_PRIVATE_KEY` | All | Tauri updater minisign private key (for OTA bundle integrity) |
| `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` | All | Passphrase protecting the updater private key |
| `APPLE_CERTIFICATE` | macOS | base64-encoded `.p12` Developer ID Application certificate |
| `APPLE_CERTIFICATE_PASSWORD` | macOS | passphrase for the `.p12` |
| `APPLE_SIGNING_IDENTITY` | macOS | Common Name, e.g. `Developer ID Application: MyrmAgent Team (TEAMID)` |
| `APPLE_ID` | macOS | Apple ID email used to enroll Developer Program |
| `APPLE_PASSWORD` | macOS | app-specific password generated at appleid.apple.com |
| `APPLE_TEAM_ID` | macOS | 10-character Team ID from Apple Developer membership |
| `KEYCHAIN_PASSWORD` | macOS | passphrase for the temporary build keychain (random per-build is fine) |
| `AZURE_TENANT_ID` | Win (preferred) | Azure AD tenant containing your Trusted Signing account |
| `AZURE_CLIENT_ID` | Win (preferred) | Azure AD service principal client id |
| `AZURE_CLIENT_SECRET` | Win (preferred) | Azure AD service principal secret |
| `AZURE_TRUSTED_SIGNING_ENDPOINT` | Win (preferred) | e.g. `https://eus.codesigning.azure.net` |
| `AZURE_TRUSTED_SIGNING_ACCOUNT` | Win (preferred) | the Trusted Signing account name |
| `AZURE_TRUSTED_SIGNING_CERT_PROFILE` | Win (preferred) | the certificate profile name |
| `WINDOWS_CERTIFICATE` | Win (fallback) | base64-encoded `.pfx` Authenticode certificate |
| `WINDOWS_CERTIFICATE_PASSWORD` | Win (fallback) | passphrase for the `.pfx` |

> **Choose Azure Trusted Signing for Windows.** It keeps the private key inside Azure Key Vault and the workflow only obtains short-lived signing tokens — strictly safer than `.pfx` base64 sitting in GitHub Secrets. PFX is a tested fallback if Azure access is unavailable.

---

## Tauri Updater Signing (all platforms)

Tauri's updater verifies bundle artifacts against the public key embedded in the app. Generate once and commit only the **public** half.

```bash
cd myrm-agent-desktop
bun x @tauri-apps/cli signer generate -w ~/.tauri/myrmagent.key
```

Outputs:

- `~/.tauri/myrmagent.key` — **private** key. Never commit. Set a passphrase when prompted.
- `~/.tauri/myrmagent.key.pub` — paste into `src-tauri/tauri.conf.json#plugins.updater.pubkey`, replacing the placeholder `UNSAFE_UPDATER_PUBKEY_PLACEHOLDER_GENERATE_BEFORE_RELEASE`.

Then set:

- `TAURI_SIGNING_PRIVATE_KEY` — full contents of `~/.tauri/myrmagent.key`
- `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` — the passphrase

The workflow exports both as env vars; `tauri-action` picks them up and signs the per-platform update bundle automatically.

### Runtime Placeholder Guard

`src-tauri/src/utils/updater_safety.rs` validates the embedded pubkey at startup:

- **Dev build with placeholder**: warning emitted, OTA gracefully disabled.
- **Production build with placeholder**: error logged, OTA refused (avoids supply-chain risk where attackers could substitute a malicious update bundle against an unsigned pubkey).
- **Real pubkey**: OTA enabled.

This means **forgetting to replace the placeholder before tagging a release is automatically detected**.

---

## macOS — Developer ID + Notarization

Two separate signatures are required for a warning-free install:

1. **Code signing** with a Developer ID Application certificate — proves the bundle came from a paid Apple Developer account.
2. **Notarization** — Apple's automated malware scan, returns a ticket that gets stapled into the `.dmg` / `.app`.

### One-time: certificate

Enroll in the [Apple Developer Program] ($99/yr). In Xcode → Settings → Accounts → Manage Certificates, create a `Developer ID Application` cert. Export from Keychain as a `.p12` with a passphrase.

```bash
base64 -i MyrmAgentDeveloperID.p12 -o cert.p12.b64
```

### One-time: app-specific password for notarytool

Notarization uses the Apple ID, not the cert. At <https://appleid.apple.com> → Sign-In and Security → App-Specific Passwords, generate one labelled "myrmagent notarytool". Save it — Apple only shows it once.

### Hardened Runtime entitlements

`src-tauri/entitlements.plist` declares the minimum capabilities MyrmAgent.app needs to run after signing:

- **`com.apple.security.cs.allow-jit`** + **`com.apple.security.cs.allow-unsigned-executable-memory`** — required by the embedded WebView V8 engine.
- **`com.apple.security.cs.allow-dyld-environment-variables`** + **`com.apple.security.cs.disable-library-validation`** — required for Python sidecar dynamic loading.
- **`com.apple.security.automation.apple-events`** — required by Appshot's `osascript` window text extraction.

Without these entitlements, Apple Notary Service still signs successfully but **runtime functionality silently fails** (Appshot crashes, sidecar refuses to spawn, global shortcuts cannot register). The plist is the minimum set; adding more triggers extra Apple notary review.

> Note on child processes: `com.apple.security.inherit` is an **App Sandbox** entitlement and has no effect under Hardened Runtime. The Python sidecar is a bundle resource and is not signed by `tauri-action`; see "Sidecar packaging and verification runs" for what Developer ID signing needs.

TCC permissions (screen recording, accessibility, microphone) are **not** declared here — they are granted by the user at first-use prompt. `tauri.conf.json#bundle.macOS.extendInfo` provides `NSMicrophoneUsageDescription` and `NSAppleEventsUsageDescription` so the macOS TCC dialog shows a clear usage reason when the permission prompt appears.

### Verify locally before pushing the tag

After downloading the signed artifact:

```bash
spctl -a -t open --context context:primary-signature -vvv MyrmAgent_0.1.0_aarch64.dmg
# expected: source=Notarized Developer ID

codesign --verify --deep --strict --verbose=2 /Applications/MyrmAgent.app
# expected: valid on disk + satisfies its Designated Requirement

codesign -d --entitlements - /Applications/MyrmAgent.app
# expected: entitlements XML matches src-tauri/entitlements.plist
```

[Apple Developer Program]: https://developer.apple.com/programs/

### Automated CI verification

`build-macos-arm`, `build-windows` and `build-linux` in `.github/workflows/desktop-release.yml` run `scripts/ci/desktop-release/smoke_launch_shell.py --bundle <dir>` after `tauri build`: on macOS twice (the `.app` and the extracted updater tarball, which is what an auto-updated user receives), on Windows against the silent NSIS install, on Linux against the extracted AppImage under `xvfb-run`. The script starts the packaged shell itself with what a user's launch gives it: the launcher's working directory (`/` on macOS, the install directory on Windows, and on Linux whatever AppRun changes into), a PATH without Node.js, and on macOS and Linux a fresh profile directory. It requires that the shell brings up the Python backend (`:8080/health`) and the bundled Next server (`:13000`, serving a page whose `/_next/static` asset is served too) within 180 s, that both stay up for 5 s, and that both are gone when the shell quits (SIGTERM on macOS and Linux; Windows has no graceful signal, so the tree is killed and neither port may still be served). A failure prints the tail of the shell's log.

`scripts/verify-signing.sh` is the verifier for a signed macOS release: run it right after `tauri-action` produces the `.app` / `.dmg` once the Apple secrets are configured. **No workflow invokes it today** — the release is unsigned, so every check would fail — and wiring it in is part of adopting signing. Each artifact is subjected to four hard checks:

1. `codesign --verify --deep --strict --verbose=4` — signature integrity
2. `codesign -dv --verbose=4` — signature details (audit trail in verify log)
3. `spctl --assess` — Gatekeeper acceptance simulation (`-t exec` for `.app`, `-t open` for `.dmg`)
4. `xcrun stapler validate` — Apple Notary staple presence

The script exits non-zero if any check fails and writes the full log to `--log` for postmortem inspection. This catches three classes of silent failure that `tauri-action` does not surface as non-zero exit codes:

- TEAM_ID typo causing notarization unauthorized but signing nominally succeeded
- Apple Notary Service approved the upload but the staple did not get attached
- Hardened Runtime entitlements mismatch between bundle and Notary-approved config

---

## Windows — Authenticode (Azure Trusted Signing preferred)

### How Windows Signing Works

Tauri v2 supports two mechanisms for Windows code signing. Neither is automatic — both require explicit CI workflow steps beyond setting environment variables.

1. **`signCommand`** — Tauri invokes a custom command for every binary and installer. Use this for Azure Trusted Signing or any HSM/cloud-based signing tool.
2. **PFX certificate import** — Import a `.pfx` into the Windows certificate store, then configure `certificateThumbprint` in `tauri.conf.json`. Tauri's bundler uses `signtool.exe` with the installed certificate.
3. **No signing** — workflow still builds an unsigned `.exe`/`.msi`.

### Option A — Azure Trusted Signing (recommended)

Private key lives in Azure Key Vault HSM. The workflow installs a signing CLI and configures Tauri's `signCommand`.

1. Subscribe to [Azure Trusted Signing] (≈ $9.99/month base).
2. Create an Azure AD service principal with `Trusted Signing Certificate Profile Signer` role.
3. Set `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` as repo secrets (the CLI reads these automatically).
4. Add a CI step to install the signing CLI: `cargo install trusted-signing-cli`.
5. Add a CI step to inject `signCommand` into `tauri.conf.json` before building:
   ```json
   { "bundle": { "windows": { "signCommand": "trusted-signing-cli -e <ENDPOINT> -a <ACCOUNT> -c <PROFILE> %1" } } }
   ```
6. The `tauri build` command invokes the `signCommand` for every `.exe` and `.msi` artifact.

[Azure Trusted Signing]: https://learn.microsoft.com/en-us/azure/trusted-signing/

### Option B — Authenticode PFX (fallback)

Order a **code signing certificate** from a CA Microsoft trusts (DigiCert, Sectigo, SSL.com, …). EV certs avoid SmartScreen reputation ramp; OV certs work but warn until enough installs build trust.

```bash
openssl pkcs12 -export \
  -inkey myrmagent.key \
  -in myrmagent.cer \
  -out myrmagent.pfx \
  -name "MyrmAgent Code Signing"

base64 -w0 myrmagent.pfx > myrmagent.pfx.b64
```

Set `WINDOWS_CERTIFICATE` to the base64 contents and `WINDOWS_CERTIFICATE_PASSWORD` to the PFX passphrase.

Add a CI step **before** `tauri-action` to import the certificate into the Windows certificate store:

```yaml
- name: Import Windows certificate
  if: env.WINDOWS_CERTIFICATE != ''
  env:
    WINDOWS_CERTIFICATE: ${{ secrets.WINDOWS_CERTIFICATE }}
    WINDOWS_CERTIFICATE_PASSWORD: ${{ secrets.WINDOWS_CERTIFICATE_PASSWORD }}
  shell: pwsh
  run: |
    $cert = [IO.Path]::Combine($env:RUNNER_TEMP, 'myrmagent.pfx')
    [IO.File]::WriteAllBytes($cert, [Convert]::FromBase64String($env:WINDOWS_CERTIFICATE))
    Import-PfxCertificate -FilePath $cert -CertStoreLocation Cert:\CurrentUser\My `
      -Password (ConvertTo-SecureString $env:WINDOWS_CERTIFICATE_PASSWORD -Force -AsPlainText)
    Remove-Item $cert
```

Then set `certificateThumbprint` in `tauri.conf.json` under `bundle.windows` to the SHA-1 thumbprint of the imported certificate.

### Timestamp Server (mandatory)

`tauri.conf.json` already pins `timestampUrl: http://timestamp.digicert.com`. Without timestamping, signatures **expire when the certificate expires**, breaking old installers. With timestamping, signatures remain verifiable indefinitely.

### Verify locally before pushing the tag

```powershell
signtool verify /pa /v /tw MyrmAgent_0.1.0_x64-setup.exe
```

Output should include `Successfully verified` and `The signature is timestamped`.

### Automated CI verification

`scripts/verify-signing.ps1` is the verifier for a signed Windows release: run it after `tauri-action` produces the `.exe` / `.msi` installers once a signing certificate is configured. No workflow invokes it today; wiring it in is part of adopting signing. For each artifact:

- Runs `signtool verify /pa /v /tw <artifact>` with the Default Authentication Verification Policy
- Parses output for both `Successfully verified` and `The signature is timestamped`
- Exits non-zero if either assertion is missing, and writes the full log to `-LogPath` for postmortem inspection

This catches the case where a certificate was applied but the timestamp server was unreachable — without timestamping, the signature becomes invalid the moment the cert expires.

---

## Linux

`.deb` and `.AppImage` distribution does not require code signing. The release workflow generates SHA256 checksums alongside the artifacts for integrity verification by users.

If MyrmAgent ever publishes a Flatpak or Snap, the respective store handles signing on upload.

---

## Key Rotation

### Tauri Updater pubkey rotation

> **Warning**: Rotating the updater key invalidates every previously installed client's ability to verify updates. Avoid unless the private key is leaked.

If rotation is required:

1. Generate a new key pair: `bun x @tauri-apps/cli signer generate`
2. Ship one transitional release signed with the **old** key whose release notes tell users to download fresh installers manually.
3. Replace `tauri.conf.json#plugins.updater.pubkey` in the next release.
4. Update `TAURI_SIGNING_PRIVATE_KEY` in repo secrets.

### Code signing certificate rotation

Annual rotation cadence aligns with most CA renewal cycles. Track certificate expiry manually against the milestones below:

- **WARNING** at T-60 days: procure replacement cert
- **CRITICAL** at T-30 days: rotate immediately or release pipeline will fail

Rotation procedure:

1. Order replacement certificate from CA (or rotate Azure Trusted Signing cert profile).
2. Update the corresponding Repo Secret value.
3. Trigger a release build to verify the new cert signs correctly.

---

## 4-Eyes Emergency Response

If a signing key is suspected to be leaked:

1. **Immediate** (T+0): Revoke the cert at the CA console (or rotate the Azure Trusted Signing cert profile). All future signed installers become untrusted.
2. **T+1 hour**: Generate a fresh keypair / cert and update Repo Secrets.
3. **T+24 hours**: Cut a new release with the new cert + new updater pubkey. Add a release-note banner pointing existing users to the new download URL.
4. **T+7 days**: Audit any installers signed since suspected leak window; consider re-publishing if compromise window is large.

Minimum two senior engineers must approve any signing-key rotation outside scheduled maintenance — single-point-of-failure must be prevented.

---

## Troubleshooting

- **`errSecInternalComponent` on macOS runners** — Apple's `notarytool` needs the keychain unlocked. The workflow's `Import Apple Code Signing Certificate` step handles this; if you've inlined custom steps, add a `security unlock-keychain` step before signing.
- **"The signature of the application is invalid" on Windows after an update** — almost always means the updater's `pubkey` in `tauri.conf.json` doesn't match the private key used by the workflow. Confirm both halves come from the same `signer generate` run.
- **Azure Trusted Signing returns 401/403** — service principal lacks `Trusted Signing Certificate Profile Signer` role assignment. Re-check the role binding in Azure RBAC.
- **NSIS installer shows English despite multi-language config** — verify `bundle.windows.nsis.displayLanguageSelector: true` and that `languages` array in `tauri.conf.json` includes the target locale.
- **macOS notarization 30+ min hang** — Apple notary backend congestion. `tauri-action` retries automatically; manual workaround is to wait + retry.
- **Updater fails with `Failed to verify the signature of the update bundle`** — bundle was signed with a different `TAURI_SIGNING_PRIVATE_KEY` than the embedded `pubkey`. Rotate workflow secrets to match.

---

## Three-Deployment-Mode Synergy

MyrmAgent ships in three forms: **Local Web (Python+frontend)**, **Tauri desktop**, **SaaS via control plane**. Code signing is exclusively a Tauri-desktop concern — but its value crosses all three modes:

- **Local Web → Desktop**: web users who graduate to the desktop client must not be turned away by Gatekeeper/SmartScreen. Signing eliminates the first-install friction that costs ~58% of unsigned desktop users.
- **SaaS → Desktop**: SaaS users frequently download the desktop version. Enterprise IT departments reject unsigned applications outright. Signing unlocks B2B procurement.
- **Desktop → SaaS**: a smooth desktop first-experience is the conversion funnel for SaaS subscriptions. Removing first-install warnings boosts retention to feed SaaS upsell.

Without signing, the desktop client is the weakest link in the deployment matrix.
