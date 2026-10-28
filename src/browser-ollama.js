// Direct browser transport. Constructing this object never touches localhost.
export const OLLAMA_ORIGIN = 'http://127.0.0.1:11434';
const CONNECTION_HELP = 'Start Ollama, allow this website’s exact origin in OLLAMA_ORIGINS, and allow Local Network Access in Chrome. See Local Ollama setup below. No cloud fallback was used.';

export class BrowserOllama {
  constructor(fetcher = (...args) => fetch(...args)) {
    this.fetcher = fetcher;
    this.models = [];
    this.connected = false;
    this.controllers = new Set();
    this.generation = 0;
  }

  disconnect() {
    // Invalidate late discovery replies as well as aborting requests already in flight.
    this.generation++;
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
    this.models = [];
    this.connected = false;
  }

  async request(path, body, {signal, timeout = 120000} = {}) {
    if (!['/api/tags', '/api/chat'].includes(path)) throw Error('Unsupported local Ollama endpoint.');
    const controller = new AbortController();
    this.controllers.add(controller);
    // One controller combines caller cancellation, manual disconnect, and the per-request timeout.
    const abort = () => controller.abort();
    if (signal?.aborted) abort();
    else signal?.addEventListener('abort', abort, {once: true});
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeout);
    try {
      const response = await this.fetcher(OLLAMA_ORIGIN + path, {
        method: body ? 'POST' : 'GET', mode: 'cors', credentials: 'omit',
        cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer',
        // Unknown RequestInit members are ignored by older browsers. Current Chrome
        // accepts loopback and can request its local-network permission on this call.
        targetAddressSpace: 'loopback',
        headers: body ? {'Content-Type': 'application/json'} : {},
        body: body ? JSON.stringify(body) : undefined, signal: controller.signal,
      });
      if (!response.ok) {
        if (response.status === 403) throw Error('Ollama rejected this website’s origin. ' + CONNECTION_HELP);
        if (response.status === 404) throw Error('Ollama could not find that model or endpoint. Reconnect and choose an installed model.');
        throw Error('Ollama could not complete the request. Check model memory and Ollama logs. ' + CONNECTION_HELP);
      }
      // Do not allow a local service to fill browser memory with an unbounded reply.
      const reader = response.body.getReader();
      const chunks = [];
      let size = 0;
      try {
        while (true) {
          const {done, value} = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > 256 * 1024) {
            await reader.cancel();
            throw Error('Ollama response is too large. Choose a smaller model response.');
          }
          chunks.push(value);
        }
      } finally {
        reader.releaseLock();
      }
      const bytes = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
      try { return JSON.parse(new TextDecoder().decode(bytes)); }
      catch { throw Error('Ollama returned an unreadable response. Reconnect and try again.'); }
    } catch (error) {
      if (timedOut) throw Error('Local Ollama timed out. Wait for the model to load or choose a smaller model. No cloud fallback was used.');
      if (controller.signal.aborted) throw Error('Local Ollama request cancelled.');
      if (error instanceof TypeError) throw Error('The browser could not reach local Ollama. ' + CONNECTION_HELP);
      throw error;
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      this.controllers.delete(controller);
    }
  }

  async connect() {
    this.disconnect();
    const generation = this.generation;
    const result = await this.request('/api/tags', null, {timeout: 15000});
    if (generation !== this.generation) throw Error('Local Ollama connection cancelled.');
    if (!Array.isArray(result.models)) throw Error('Ollama returned an invalid model list.');
    // Offer only downloaded local models; cloud-linked entries must not disguise remote inference as local.
    this.models = [...new Set(result.models.filter(model =>
      model && typeof model.name === 'string' && /^[A-Za-z0-9][A-Za-z0-9._/:+-]{0,199}$/.test(model.name) &&
      !model.remote_host && !model.remote_model && !model.name.toLowerCase().includes(':cloud') &&
      !model.details?.families?.includes('cloud')
    ).map(model => model.name))].slice(0, 100);
    this.connected = true;
    return this.models;
  }

  async chat(inference, {signal} = {}) {
    if (!this.connected || !this.models.includes(inference?.model)) throw Error('Connect Local Ollama and choose an installed local model first.');
    if (!Array.isArray(inference.messages) || !inference.format) throw Error('Invalid analysis request.');
    // Rebuild the body: server-supplied URL/auth/tools/options cannot alter the transport.
    const body = {model: inference.model, messages: inference.messages, format: inference.format,
      stream: false, options: {temperature: 0, num_predict: 1200, num_ctx: 8192}};
    if (inference.model.toLowerCase().startsWith('qwen3')) body.think = false;
    const result = await this.request('/api/chat', body, {signal});
    if (result.done_reason === 'length') throw Error('Ollama reached its output limit. Try a simpler question.');
    if (typeof result.message?.content !== 'string' || !result.message.content.trim() || result.message.content.length > 16000) {
      throw Error('Ollama returned an empty or oversized analysis action. Try another local model.');
    }
    return result.message.content;
  }
}

// The server issues prompts and verifies every model action; the browser only transports text.
export async function runBrowserAnalyst(api, ollama, payload, {signal} = {}) {
  let runId;
  try {
    let packet = await api('/api/ollama-start', {...payload, provider: 'browser_ollama'}, {signal});
    for (let turn = 0; turn <= 6; turn++) {
      if (signal?.aborted) throw Error('Local analysis cancelled.');
      if (packet.status === 'complete') return packet.result;
      if (packet.status !== 'model_required' || !packet.runId || !packet.step) throw Error('Invalid local analysis step.');
      runId = packet.runId;
      // The opaque step token binds this model reply to the server's next expected action.
      const output = await ollama.chat(packet.inference, {signal});
      packet = await api('/api/ollama-step', {runId, step: packet.step, output}, {signal});
    }
    throw Error('Local analysis reached its step limit. Ask a more specific question.');
  } finally {
    if (runId) {
      // Best effort without the cancelled signal; expiry bounds abandoned runs if offline.
      try { await api('/api/ollama-cancel', {runId}, {signal: AbortSignal.timeout(5000)}); } catch { /* server expiry handles cleanup */ }
    }
  }
}
