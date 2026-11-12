// Stand-in for Chrome's --remote-debugging-pipe end, used as the proxy's `--chrome-path`.
//
// The proxy talks NUL-terminated JSON over fd 3 (proxy -> Chrome) and fd 4 (Chrome -> proxy).
// This process relays both directions to the test over TCP (one JSON object per line), so the test
// plays Chrome: it sees every request the proxy forwards and decides every reply and event.
import net from 'node:net';

const PIPE_FROM_PROXY = 3;
const PIPE_TO_PROXY = 4;

const control = net.connect({ host: '127.0.0.1', port: Number(process.env.FAKE_CHROME_CONTROL_PORT) });
const fromProxy = new net.Socket({ fd: PIPE_FROM_PROXY, readable: true, writable: false });
const toProxy = new net.Socket({ fd: PIPE_TO_PROXY, readable: false, writable: true });

let frames = Buffer.alloc(0);
fromProxy.on('data', (chunk) => {
    frames = Buffer.concat([frames, chunk]);
    let end;
    while ((end = frames.indexOf(0)) !== -1) {
        const frame = frames.subarray(0, end);
        frames = frames.subarray(end + 1);
        if (frame.length) control.write(`${JSON.stringify({ fromProxy: JSON.parse(frame.toString('utf8')) })}\n`);
    }
});

let lines = '';
control.on('data', (chunk) => {
    lines += chunk.toString('utf8');
    let end;
    while ((end = lines.indexOf('\n')) !== -1) {
        const line = lines.slice(0, end);
        lines = lines.slice(end + 1);
        if (!line) continue;
        const { toProxy: message, exit } = JSON.parse(line);
        if (message) toProxy.write(`${JSON.stringify(message)}\0`);
        if (exit !== undefined) process.exit(exit);
    }
});

// Either end going away means there is nothing left to relay; never outlive the proxy or the test.
fromProxy.on('close', () => process.exit(0));
control.on('close', () => process.exit(0));
control.on('error', () => process.exit(1));
