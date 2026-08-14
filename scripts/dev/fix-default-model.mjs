/**
 * One-shot maintenance fix: point the global default base model to a
 * currently reachable model (agnes-2.5-flash) because the previously
 * configured default (deepseek-v4-flash) returns 503 from the remote
 * gateway. Preserves every other provider/defaultModelConfig field.
 */
const apiBase = process.env.E2E_API_BASE ?? 'http://127.0.0.1:8080';
const deviceId = process.env.E2E_CONFIG_DEVICE_ID ?? 'default-model-fix';

async function apiFetch(path, options = {}) {
  const res = await fetch(`${apiBase}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  });
  return res;
}

const read = await apiFetch('/api/v1/config/providers');
if (!read.ok) {
  throw new Error(`GET providers failed: ${read.status} ${await read.text()}`);
}
const body = await read.json();
const value = body?.value ?? body;
const primary = value?.defaultModelConfig?.baseModel?.primary;
if (!primary) {
  throw new Error(`No defaultModelConfig.baseModel.primary: ${JSON.stringify(value).slice(0, 300)}`);
}

const before = `${primary.providerId}/${primary.model}`;
primary.model = 'agnes-2.5-flash';
const after = `${primary.providerId}/${primary.model}`;

const putRes = await apiFetch('/api/v1/config/providers', {
  method: 'PUT',
  body: JSON.stringify({ value, deviceId }),
});
const putBody = await putRes.json();
console.log(`default base model: ${before} -> ${after} (PUT ${putRes.status})`);
if (!putRes.ok) {
  throw new Error(`PUT providers failed: ${JSON.stringify(putBody).slice(0, 400)}`);
}
const record = putBody?.value ?? putBody;
const confirm = record?.defaultModelConfig?.baseModel?.primary;
console.log(`confirmed: ${confirm?.providerId}/${confirm?.model}`);
