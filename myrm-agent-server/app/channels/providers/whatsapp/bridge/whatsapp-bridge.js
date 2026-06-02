/**
 * WhatsApp Bridge — Node.js subprocess for Python WhatsAppChannel.
 *
 * Uses @whiskeysockets/baileys 7.x for WhatsApp Web multi-device protocol.
 * Communicates with the Python parent process via JSON Lines over stdin/stdout.
 *
 * Protocol (stdout → Python):
 *   {"type":"qr","data":"2@..."}
 *   {"type":"connection","status":"open"|"close"|"reconnecting"|"logged_out","reason":"..."}
 *   {"type":"message","from":"...","text":"...","id":"...","pushName":"...","audio":{mimetype,seconds,ptt,fileLength,messageId}}
 *   {"type":"sent","nonce":"...","key":{remoteJid,id,fromMe}}  — only when send includes nonce
 *   {"type":"edit_ok","key":"..."}  — after successful edit
 *   {"type":"media_downloaded","messageId":"...","path":"...","size":N}
 *   {"type":"ready"}
 *   {"type":"error","message":"..."}
 *
 * Protocol (stdin ← Python):
 *   {"type":"send","to":"...@s.whatsapp.net","text":"...","nonce":"..."}  — nonce is optional
 *   {"type":"send_media","to":"...","media_type":"image"|"document"|"audio"|"video","path":"..."|"url":"...","mimetype":"...","fileName":"...","caption":"..."}
 *   {"type":"edit","to":"...@s.whatsapp.net","key":{remoteJid,id,fromMe},"text":"new text"}
 *   {"type":"delete","to":"...@s.whatsapp.net","key":{remoteJid,id,fromMe}}
 *   {"type":"typing","to":"...@s.whatsapp.net","status":"composing"|"paused"}
 *   {"type":"react","to":"...@g.us","messageId":"...","emoji":"👀"|""}
 *   {"type":"download_media","messageId":"..."}
 *   {"type":"list_groups"}
 *   {"type":"stop"}
 *
 * Protocol (stdout → Python) for list_groups:
 *   {"type":"groups","data":[{"jid":"...@g.us","name":"..."}]}
 */

import makeWASocket, {
  useMultiFileAuthState,
  makeCacheableSignalKeyStore,
  DisconnectReason,
  fetchLatestBaileysVersion,
  downloadMediaMessage,
} from "@whiskeysockets/baileys";
import pino from "pino";
import { createInterface } from "readline";
import { readFileSync, writeFileSync, mkdirSync, existsSync, copyFileSync, chmodSync } from "fs";
import { join } from "path";
import { tmpdir } from "os";
import http from "http";
import https from "https";
import { URL } from "url";

const AUTH_DIR = process.argv[2] || "./whatsapp_auth";
const logger = pino({ level: "silent" });

const CREDS_PATH = join(AUTH_DIR, "creds.json");
const CREDS_BACKUP_PATH = join(AUTH_DIR, "creds.json.bak");
let credsSaveQueue = Promise.resolve();

/**
 * Queue credential saves to prevent concurrent writes that could corrupt
 * the creds.json file. Each save first backs up the current valid creds.
 */
function enqueueSaveCreds(saveCreds) {
  credsSaveQueue = credsSaveQueue
    .then(() => safeSaveCreds(saveCreds))
    .catch((err) => {
      emit({ type: "error", message: `creds save error: ${err.message}` });
    });
}

async function safeSaveCreds(saveCreds) {
  try {
    if (existsSync(CREDS_PATH)) {
      const raw = readFileSync(CREDS_PATH, "utf-8");
      JSON.parse(raw);
      copyFileSync(CREDS_PATH, CREDS_BACKUP_PATH);
      try { chmodSync(CREDS_BACKUP_PATH, 0o600); } catch { /* best-effort */ }
    }
  } catch { /* keep existing backup if current creds are invalid */ }

  await Promise.resolve(saveCreds());
  try { chmodSync(CREDS_PATH, 0o600); } catch { /* best-effort */ }
}

/**
 * Restore creds.json from backup if the primary file is missing or corrupted.
 */
function maybeRestoreCredsFromBackup() {
  if (!existsSync(CREDS_BACKUP_PATH)) return;
  try {
    if (existsSync(CREDS_PATH)) {
      const raw = readFileSync(CREDS_PATH, "utf-8");
      JSON.parse(raw);
      return;
    }
  } catch { /* primary creds corrupted, restore from backup */ }

  try {
    const backupRaw = readFileSync(CREDS_BACKUP_PATH, "utf-8");
    JSON.parse(backupRaw);
    copyFileSync(CREDS_BACKUP_PATH, CREDS_PATH);
    try { chmodSync(CREDS_PATH, 0o600); } catch { /* best-effort */ }
    emit({ type: "info", message: "Restored creds.json from backup" });
  } catch {
    emit({ type: "error", message: "Both creds.json and backup are corrupted" });
  }
}

/**
 * Build an HTTPS agent that tunnels through an HTTP proxy via CONNECT.
 * Returns undefined when no proxy is configured so Baileys uses direct
 * connections. Reads https_proxy / HTTPS_PROXY / http_proxy / HTTP_PROXY.
 */
function buildProxyAgent() {
  const proxyUrl =
    process.env.https_proxy ||
    process.env.HTTPS_PROXY ||
    process.env.http_proxy ||
    process.env.HTTP_PROXY;
  if (!proxyUrl) return undefined;

  let parsed;
  try {
    parsed = new URL(proxyUrl);
  } catch {
    emit({ type: "error", message: `Invalid proxy URL: ${proxyUrl}` });
    return undefined;
  }
  const proxyHost = parsed.hostname;
  const proxyPort = parseInt(parsed.port, 10) || 80;

  class ConnectAgent extends https.Agent {
    createConnection(options, callback) {
      const target = `${options.host}:${options.port || 443}`;
      const connectReq = http.request({
        host: proxyHost,
        port: proxyPort,
        method: "CONNECT",
        path: target,
      });
      connectReq.on("connect", (res, socket) => {
        if (res.statusCode !== 200) {
          const errMsg = `Proxy CONNECT ${target} returned ${res.statusCode}`;
          emit({ type: "error", message: errMsg });
          callback(new Error(errMsg));
          socket.destroy();
          return;
        }
        options.socket = socket;
        super.createConnection(options, callback);
      });
      connectReq.on("error", (err) => {
        emit({ type: "error", message: `Proxy CONNECT error: ${err.message}` });
        callback(err);
      });
      connectReq.end();
    }
  }

  return new ConnectAgent({ keepAlive: true });
}

function emit(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

let sock = null;
let shouldReconnect = true;
let waVersion = null;
let selfJid = null;
const lidToPnCache = new Map();

const FUTURE_PROOF_KEYS = [
  "botInvokeMessage",
  "ephemeralMessage",
  "viewOnceMessage",
  "viewOnceMessageV2",
  "viewOnceMessageV2Extension",
  "documentWithCaptionMessage",
  "editedMessage",
  "groupMentionedMessage",
  "lottieStickerMessage",
];

function unwrapFutureProof(message) {
  if (!message) return message;
  for (const key of FUTURE_PROOF_KEYS) {
    if (message[key]?.message) {
      return unwrapFutureProof(message[key].message);
    }
  }
  return message;
}

function isReplyToBot(contextInfo) {
  if (!contextInfo?.participant || !selfJid) return false;
  const quotedSender = contextInfo.participant;
  const selfNum = selfJid.split(":")[0];
  const quotedNum = quotedSender.split("@")[0].split(":")[0];
  if (selfNum === quotedNum) return true;
  const selfLid = sock?.user?.lid;
  if (selfLid && quotedSender === selfLid) return true;
  const resolvedPn = lidToPnCache.get(quotedSender);
  if (resolvedPn) {
    return resolvedPn.split("@")[0].split(":")[0] === selfNum;
  }
  return false;
}
const pendingMediaMessages = new Map(); // messageId → raw msg (for download_media)

function cacheLidPn(lid, pn) {
  if (!lid || !pn) return false;
  if (lidToPnCache.has(lid)) return false;
  lidToPnCache.set(lid, pn);
  emit({ type: "lid_resolved", lid, pn });
  return true;
}

function extractLidPnFromContact(contact) {
  if (!contact) return;
  const id = contact.id || "";
  const lid = contact.lid || "";
  if (id.endsWith("@s.whatsapp.net") && lid.endsWith("@lid")) {
    cacheLidPn(lid, id);
  } else if (lid.endsWith("@s.whatsapp.net") && id.endsWith("@lid")) {
    cacheLidPn(id, lid);
  }
}

async function resolveLidToPN(lid) {
  if (!lid) return null;
  const cached = lidToPnCache.get(lid);
  if (cached) return cached;
  if (!sock) return null;
  try {
    const pn = await sock.signalRepository?.lidMapping?.getPNForLID(lid);
    if (pn) {
      cacheLidPn(lid, pn);
      return pn;
    }
  } catch {
    /* mapping not available in this version */
  }
  return null;
}

async function resolveVersion() {
  if (waVersion) return waVersion;
  try {
    const { version } = await fetchLatestBaileysVersion({});
    waVersion = version;
  } catch {
    waVersion = [2, 3000, 1034238531];
  }
  return waVersion;
}

async function connectWhatsApp() {
  const version = await resolveVersion();
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  const socketOpts = {
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    version,
    logger,
    browser: ["MyrmAgent", "Desktop", "1.0.0"],
    printQRInTerminal: false,
    syncFullHistory: false,
    markOnlineOnConnect: false,
  };

  const proxyAgent = buildProxyAgent();
  if (proxyAgent) {
    socketOpts.agent = proxyAgent;
    emit({ type: "info", message: "Using HTTP proxy for WhatsApp connection" });
  }

  sock = makeWASocket(socketOpts);

  if (sock.ws && typeof sock.ws.on === "function") {
    sock.ws.on("error", (err) => {
      emit({ type: "error", message: `WebSocket error: ${err.message}` });
    });
  }

  sock.ev.on("creds.update", () => enqueueSaveCreds(saveCreds));

  sock.ev.on("connection.update", (update) => {
    try {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        emit({ type: "qr", data: qr });
      }

      if (connection === "open") {
        selfJid = sock?.user?.id || null;
        const selfLid = sock?.user?.lid || null;
        console.error('[WhatsApp Bridge] Connection OPEN! selfJid:', selfJid, 'selfLid:', selfLid);
        if (selfJid && selfLid) {
          const pnJid = `${selfJid.split(":")[0]}@s.whatsapp.net`;
          cacheLidPn(selfLid, pnJid);
        }
        console.error('[WhatsApp Bridge] Emitting connection event to Python');
        emit({ type: "connection", status: "open", selfJid, selfLid });
        console.error('[WhatsApp Bridge] Connection event emitted');
      }

      if (connection === "close") {
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        const reason = lastDisconnect?.error?.message || "unknown";

        if (statusCode === DisconnectReason.restartRequired && shouldReconnect) {
          emit({ type: "connection", status: "reconnecting", reason });
          connectWhatsApp();
        } else if (statusCode === DisconnectReason.loggedOut) {
          emit({ type: "connection", status: "logged_out", reason });
          shouldReconnect = false;
        } else if (shouldReconnect) {
          emit({ type: "connection", status: "close", reason });
          setTimeout(() => connectWhatsApp(), 5000);
        } else {
          emit({ type: "connection", status: "close", reason });
        }
      }
    } catch (err) {
      emit({ type: "error", message: `connection.update handler: ${err.message}` });
    }
  });

  for (const evName of ["contacts.upsert", "contacts.update", "contacts.set"]) {
    sock.ev.on(evName, (contacts) => {
      const arr = Array.isArray(contacts) ? contacts : [];
      for (const c of arr) extractLidPnFromContact(c);
    });
  }

  sock.ev.on("messaging-history.set", (data) => {
    for (const c of data?.contacts || []) extractLidPnFromContact(c);
  });

  sock.ev.on("messages.upsert", async ({ messages }) => {
    for (const msg of messages) {
      try {
        const unwrapped = unwrapFutureProof(msg.message);
        
        console.error('[WhatsApp Bridge] === Message Debug ===');
        console.error('[WhatsApp Bridge] Raw message keys:', Object.keys(unwrapped || {}));
        console.error('[WhatsApp Bridge] Full unwrapped:', JSON.stringify(unwrapped, null, 2));
        
        const text =
          unwrapped?.conversation ||
          unwrapped?.extendedTextMessage?.text ||
          unwrapped?.imageMessage?.caption ||
          unwrapped?.videoMessage?.caption ||
          unwrapped?.documentMessage?.caption ||
          null;

        const audioMsg = unwrapped?.audioMessage || null;
        const documentMsg = unwrapped?.documentMessage || null;
        const hasContent = text || audioMsg || documentMsg;
        
        console.error('[WhatsApp Bridge] Extracted text:', text);
        console.error('[WhatsApp Bridge] Has audio:', !!audioMsg);
        console.error('[WhatsApp Bridge] Has content:', hasContent);
        console.error('[WhatsApp Bridge] === End Debug ===');
        
        if (!hasContent) continue;

        const remoteJid = msg.key.remoteJid || "";
        const isGroup = remoteJid.endsWith("@g.us");

        if (msg.key.fromMe) {
          if (text && text.startsWith("[Myrm AI] ")) continue;
          if (!isGroup) {
            const selfNum = selfJid ? selfJid.split(":")[0] : null;
            const remoteNum = remoteJid.split("@")[0].split(":")[0];
            const isSelfChat =
              (selfNum && remoteNum === selfNum) || remoteJid.endsWith("@lid");
            if (!isSelfChat) continue;
          }
          if (isGroup) continue;
        }

        const ctxInfo = unwrapped?.extendedTextMessage?.contextInfo || null;
        const mentionedJids = ctxInfo?.mentionedJid || [];

        if (isGroup) {
          console.error('[WhatsApp Bridge DEBUG] ===================');
          console.error('[WhatsApp Bridge] Message text:', text);
          console.error('[WhatsApp Bridge] selfJid:', selfJid);
          console.error('[WhatsApp Bridge] mentionedJids:', mentionedJids);
          console.error('[WhatsApp Bridge] contextInfo:', JSON.stringify(ctxInfo, null, 2));
          console.error('[WhatsApp Bridge DEBUG] ===================');
        }

        const replyToBot = isGroup && isReplyToBot(ctxInfo);

        let quotedMessage = null;
        if (ctxInfo?.quotedMessage) {
          const quotedText = ctxInfo.quotedMessage.conversation ||
                           ctxInfo.quotedMessage.extendedTextMessage?.text ||
                           "[媒体消息]";
          quotedMessage = {
            message_id: ctxInfo.stanzaId || null,
            content: quotedText,
            sender_id: ctxInfo.participant || null,
            sender_name: null,
          };
        }

        const fromAlt = remoteJid.endsWith("@lid")
          ? await resolveLidToPN(remoteJid)
          : null;
        const participantAlt = msg.key.participant?.endsWith("@lid")
          ? await resolveLidToPN(msg.key.participant)
          : null;

        const payload = {
          type: "message",
          from: remoteJid,
          fromAlt,
          text: text || "",
          id: msg.key.id,
          participant: msg.key.participant || null,
          participantAlt,
          pushName: msg.pushName || null,
          fromMe: !!msg.key.fromMe,
          isGroup,
          mentionedJids: isGroup ? mentionedJids : [],
          replyToBot,
          quotedMessage,
          timestamp: msg.messageTimestamp || null,
        };

        if (audioMsg) {
          payload.audio = {
            mimetype: audioMsg.mimetype || "audio/ogg",
            seconds: audioMsg.seconds || 0,
            ptt: !!audioMsg.ptt,
            fileLength: Number(audioMsg.fileLength || 0),
            messageId: msg.key.id,
          };
          pendingMediaMessages.set(msg.key.id, msg);
        }

        if (documentMsg) {
          payload.document = {
            mimetype: documentMsg.mimetype || "application/octet-stream",
            fileName: documentMsg.fileName || "document",
            fileLength: Number(documentMsg.fileLength || 0),
            caption: documentMsg.caption || null,
            messageId: msg.key.id,
          };
          pendingMediaMessages.set(msg.key.id, msg);
        }

        console.error('[WhatsApp Bridge] Sending payload:', JSON.stringify(payload, null, 2));
        emit(payload);
      } catch (err) {
        emit({ type: "error", message: `messages.upsert handler: ${err.message}` });
      }
    }
  });

  sock.ev.on("messages.reaction", (reactions) => {
    for (const { key, reaction } of reactions) {
      if (!reaction || !reaction.text) continue;
      const from = reaction.key?.remoteJid || key?.remoteJid || "";
      const messageId = key?.id || "";
      emit({
        type: "reaction",
        emoji: reaction.text,
        from,
        messageId,
      });
    }
  });

  emit({ type: "ready" });
}

const rl = createInterface({ input: process.stdin });
rl.on("line", async (line) => {
  try {
    const cmd = JSON.parse(line);

    if (cmd.type === "send" && sock) {
      const jid = cmd.to.includes("@") ? cmd.to : `${cmd.to}@s.whatsapp.net`;
      const sent = await sock.sendMessage(jid, { text: cmd.text });
      if (cmd.nonce && sent?.key) {
        emit({ type: "sent", nonce: cmd.nonce, key: sent.key });
      }
    }

    if (cmd.type === "send_media" && sock) {
      const jid = cmd.to.includes("@") ? cmd.to : `${cmd.to}@s.whatsapp.net`;
      const mediaContent = cmd.path ? readFileSync(cmd.path) : { url: cmd.url };
      const msgContent = { [cmd.media_type]: mediaContent };
      if (cmd.mimetype) msgContent.mimetype = cmd.mimetype;
      if (cmd.filename) msgContent.fileName = cmd.filename;
      if (cmd.caption) msgContent.caption = cmd.caption;
      try {
        await sock.sendMessage(jid, msgContent);
      } catch (mediaErr) {
        emit({
          type: "error",
          message: `send_media failed: ${mediaErr.message}`,
        });
      }
    }

    if (cmd.type === "edit" && sock && cmd.key) {
      const jid = cmd.to.includes("@") ? cmd.to : `${cmd.to}@s.whatsapp.net`;
      try {
        await sock.sendMessage(jid, { text: cmd.text, edit: cmd.key });
        emit({ type: "edit_ok", key: JSON.stringify(cmd.key) });
      } catch (editErr) {
        emit({ type: "error", message: `edit failed: ${editErr.message}` });
      }
    }

    if (cmd.type === "delete" && sock && cmd.key) {
      const jid = cmd.to.includes("@") ? cmd.to : `${cmd.to}@s.whatsapp.net`;
      try {
        await sock.sendMessage(jid, { delete: cmd.key });
      } catch (delErr) {
        emit({ type: "error", message: `delete failed: ${delErr.message}` });
      }
    }

    if (cmd.type === "typing" && sock) {
      const jid = cmd.to.includes("@") ? cmd.to : `${cmd.to}@s.whatsapp.net`;
      const status = cmd.status === "paused" ? "paused" : "composing";
      await sock.sendPresenceUpdate(status, jid);
    }

    if (cmd.type === "react" && sock) {
      const jid = cmd.to.includes("@") ? cmd.to : `${cmd.to}@s.whatsapp.net`;
      await sock.sendMessage(jid, {
        react: {
          text: cmd.emoji || "",
          key: { remoteJid: jid, id: cmd.messageId },
        },
      });
    }

    if (cmd.type === "resolve_pns") {
      // Contact-based LID mapping is now automatic via contacts.upsert events.
      // This command is kept for protocol compatibility but is a no-op.
    }

    if (cmd.type === "download_media" && sock) {
      const rawMsg = pendingMediaMessages.get(cmd.messageId);
      if (!rawMsg) {
        emit({
          type: "error",
          message: `download_media: message ${cmd.messageId} not found in cache`,
        });
      } else {
        try {
          const buffer = await downloadMediaMessage(
            rawMsg,
            "buffer",
            {},
            { logger, reuploadRequest: sock.updateMediaMessage },
          );
          const unwrappedRaw = unwrapFutureProof(rawMsg.message);
          const ext = (unwrappedRaw?.audioMessage?.mimetype || "").includes(
            "ogg",
          )
            ? ".ogg"
            : ".mp3";
          const mediaDir = join(tmpdir(), "myrm-voice");
          mkdirSync(mediaDir, { recursive: true });
          const filePath = join(mediaDir, `${cmd.messageId}${ext}`);
          writeFileSync(filePath, buffer);
          pendingMediaMessages.delete(cmd.messageId);
          emit({
            type: "media_downloaded",
            messageId: cmd.messageId,
            path: filePath,
            size: buffer.length,
          });
        } catch (dlErr) {
          emit({
            type: "error",
            message: `download_media failed: ${dlErr.message}`,
          });
        }
      }
    }

    if (cmd.type === "list_groups" && sock) {
      try {
        const groups = await sock.groupFetchAllParticipating();
        const data = Object.entries(groups).map(([jid, meta]) => ({
          jid,
          name: meta.subject || jid,
        }));
        emit({ type: "groups", data });
      } catch (err) {
        emit({ type: "groups", data: [], error: err.message });
      }
    }

    if (cmd.type === "stop") {
      shouldReconnect = false;
      if (sock) {
        sock.end(undefined);
      }
      process.exit(0);
    }
  } catch (err) {
    emit({ type: "error", message: err.message });
  }
});

process.on("SIGTERM", () => {
  shouldReconnect = false;
  if (sock) sock.end(undefined);
  process.exit(0);
});

maybeRestoreCredsFromBackup();
connectWhatsApp().catch((err) => {
  emit({ type: "error", message: err.message });
  process.exit(1);
});
