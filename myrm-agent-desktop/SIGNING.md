# Desktop Code Signing & Notarization

Walkthrough for shipping a signed and notarized MyrmAgent desktop bundle across macOS, Windows, and Linux.

The release workflow at `.github/workflows/desktop-release.yml` consumes every credential below from repository **Secrets** — nothing in this repo holds keys.

Without secrets set, the workflow still produces installers, but they will be unsigned (macOS shows "damaged" warning; Windows triggers SmartScreen). For production releases, **all secrets must be present**.

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
- **`com.apple.security.cs.allow-dyld-environment-variables`** + **`com.apple.security.cs.disable-library-validation`** — required for Python/Node sidecar dynamic loading.
- **`com.apple.security.automation.apple-events`** — required by Appshot's `osascript` window text extraction.

Without these entitlements, Apple Notary Service still signs successfully but **runtime functionality silently fails** (Appshot crashes, sidecar refuses to spawn, global shortcuts cannot register). The plist is the minimum set; adding more triggers extra Apple notary review.

> Note on child processes: `com.apple.security.inherit` is an **App Sandbox** entitlement and has no effect under Hardened Runtime. Python sidecar and Node Agent Runner are signed independently by `tauri-action` during bundling; the embedded binaries are co-signed using the same Developer ID so they pass Gatekeeper on launch.

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

`scripts/verify-signing.sh` runs inside `.github/workflows/tauri-release.yml` immediately after `tauri-action` produces `.app` / `.dmg` artifacts. Each artifact is subjected to four hard checks:

1. `codesign --verify --deep --strict --verbose=4` — signature integrity
2. `codesign -dv --verbose=4` — signature details (audit trail in verify log)
3. `spctl --assess` — Gatekeeper acceptance simulation (`-t exec` for `.app`, `-t open` for `.dmg`)
4. `xcrun stapler validate` — Apple Notary staple presence

The step **fails the build** if any check fails. Verification log is uploaded as the `verify-signing-macos-*` artifact for postmortem inspection. This catches three classes of silent failure that `tauri-action` does not surface as non-zero exit codes:

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

`scripts/verify-signing.ps1` runs inside `.github/workflows/tauri-release.yml` after `tauri-action` produces `.exe` / `.msi` installers. For each artifact:

- Runs `signtool verify /pa /v /tw <artifact>` with the Default Authentication Verification Policy
- Parses output for both `Successfully verified` and `The signature is timestamped`
- Fails the build if either assertion is missing

Verification log is uploaded as the `verify-signing-windows-latest` artifact. This catches the case where a certificate was applied but the timestamp server was unreachable — without timestamping, the signature becomes invalid the moment the cert expires.

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

Annual rotation cadence aligns with most CA renewal cycles. The `cert-expiry-check.yml` workflow auto-monitors expiry and creates GitHub Issues:

- **WARNING** at T-60 days: procure replacement cert
- **CRITICAL** at T-30 days: rotate immediately or release pipeline will fail

Rotation procedure:

1. Order replacement certificate from CA (or rotate Azure Trusted Signing cert profile).
2. Update the corresponding Repo Secret value.
3. Trigger a workflow run to verify the new cert; the auto-monitor issue self-closes when status returns to `ok`.

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
