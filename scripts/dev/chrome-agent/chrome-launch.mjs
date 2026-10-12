/**
 * chrome-launch — launch flags and profile hygiene for the pipe-connected ChromeAgent.
 */

import fs from 'fs';
import path from 'path';

export function buildChromeLaunchArgs({ userDataDir, initialUrl, foreground }) {
    const chromeArgs = [
        `--user-data-dir=${userDataDir}`,
        '--remote-debugging-pipe',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-features=DialMediaRouteProvider,MacAppCodeSignClone',
        // Silence crash recovery bubble & crash reports
        '--disable-session-crashed-bubble',
        '--disable-infobars',
        '--hide-crash-restore-bubble',
        '--disable-breakpad',
        '--no-crash-upload',
        // Keep ChromeAgent alive when the last window closes (macOS Cmd+W).
        '--keep-alive-for-test',
        // E2E-parity render flags: occluded/offscreen windows must keep rAF
        // so X lazy-load / scroll extraction still works (cdp-plane TAB-6b).
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-background-timer-throttling',
    ];
    if (!foreground) {
        chromeArgs.push('--window-position=-24000,-24000');
    }
    if (initialUrl) {
        chromeArgs.push(initialUrl);
    }
    return chromeArgs;
}

/** Mark the profile as cleanly exited so Chrome does not show the restore bubble. */
export function resetProfileCrashFlags(userDataDir) {
    const candidateRelPaths = [
        path.join('Default', 'Preferences'),
        path.join('Profile 1', 'Preferences'),
    ];
    for (const rel of candidateRelPaths) {
        const fullPath = path.join(userDataDir, rel);
        if (!fs.existsSync(fullPath)) continue;
        try {
            const data = JSON.parse(fs.readFileSync(fullPath, 'utf8'));
            if (data && typeof data === 'object' && data.profile && typeof data.profile === 'object') {
                data.profile.exit_type = 'Normal';
                data.profile.exited_cleanly = true;
                fs.writeFileSync(fullPath, JSON.stringify(data));
            }
        } catch {}
    }
}
