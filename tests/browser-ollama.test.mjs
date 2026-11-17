import test from 'node:test';
import assert from 'node:assert/strict';
import {BrowserOllama, runBrowserAnalyst, OLLAMA_ORIGIN} from '../src/browser-ollama.js';
import {answerModeNotice, answerOptions, chooseAnswerMode} from '../src/ai-options.js';

const response = object => new Response(JSON.stringify(object));
const inference = {model: 'llama3.2:3b', messages: [{role:'user', content:'data'}], format: {type:'object'}};

test('construction and cloud discovery never trigger local-network access', () => {
  let calls = 0;
  new BrowserOllama(() => { calls++; });
  answerOptions({options: [{provider:'groq', model:'cloud', available:true}]});
  assert.equal(calls, 0);
});

test('explicit discovery uses fixed loopback, no credentials/redirects, and excludes remote models', async () => {
  const calls = [];
  const client = new BrowserOllama(async (...args) => {
    calls.push(args);
    return response({models: [{name:'llama3.2:3b'}, {name:'remote:cloud'}, {name:'cloud-copy', remote_host:'https://elsewhere'}, {name:'linked', remote_model:'other'}, {name:'llama3.2:3b'}]});
  });
  assert.deepEqual(await client.connect(), ['llama3.2:3b']);
  assert.equal(calls[0][0], OLLAMA_ORIGIN + '/api/tags');
  assert.equal(calls[0][1].targetAddressSpace, 'loopback');
  assert.equal(calls[0][1].credentials, 'omit');
  assert.equal(calls[0][1].redirect, 'error');
  assert.deepEqual(calls[0][1].headers, {});
  client.disconnect();
  assert.equal(client.connected, false);
  assert.deepEqual(client.models, []);
});

test('local inference preserves JSON schema and never forwards auth/URLs/tools from a prompt', async () => {
  const calls = [];
  const client = new BrowserOllama(async (url, options) => {
    calls.push([url, options]);
    return response(calls.length === 1 ? {models:[{name: inference.model}]} : {message:{content:'{"action":"answer"}'}});
  });
  await client.connect();
  assert.equal(await client.chat({...inference, url:'https://evil.example', headers:{Authorization:'secret'}, tools:['unsafe']}), '{"action":"answer"}');
  const [url, options] = calls[1];
  assert.equal(url, OLLAMA_ORIGIN + '/api/chat');
  const body = JSON.parse(options.body);
  assert.deepEqual(body.format, inference.format);
  assert.equal(body.stream, false);
  assert.equal(body.tools, undefined);
  assert.equal(body.headers, undefined);
  await assert.rejects(client.chat({...inference, model:'missing'}), /installed/);
});

test('CORS, origin rejection, malformed JSON, and missing models have actionable messages', async () => {
  await assert.rejects(new BrowserOllama(async () => { throw new TypeError('Failed to fetch'); }).connect(), /OLLAMA_ORIGINS.*Chrome/);
  await assert.rejects(new BrowserOllama(async () => new Response('', {status:403})).connect(), /origin/);
  await assert.rejects(new BrowserOllama(async () => new Response('not json')).connect(), /unreadable/);
  const empty = new BrowserOllama(async () => response({models:[]}));
  assert.deepEqual(await empty.connect(), []);
  await assert.rejects(empty.chat(inference), /installed/);
});

test('overview uses bounded local settings while manual questions retain their capacity', async () => {
  const bodies = [];
  const client = new BrowserOllama(async (url, options) => {
    if (url.endsWith('/api/tags')) return response({models:[{name: inference.model}]});
    bodies.push(JSON.parse(options.body));
    return response({message:{content:'{"action":"answer"}'}});
  });
  await client.connect();
  const packet = {...inference, options:{num_predict:100000, num_ctx:100000}, keep_alive:'24h', task:'overview'};
  await client.chat(packet, {overview:true});
  await client.chat(packet);
  assert.deepEqual(bodies[0].options, {temperature:0, num_predict:450, num_ctx:4096});
  assert.equal(bodies[0].keep_alive, '5m');
  assert.deepEqual(bodies[1].options, {temperature:0, num_predict:1200, num_ctx:8192});
  assert.equal(bodies[1].keep_alive, undefined);
});

test('the original overview task selects the fast profile, not arbitrary inference options', async () => {
  const profiles = [];
  const api = async path => path.endsWith('start') ? {status:'model_required', runId:'run', step:'nonce', inference}
    : path.endsWith('step') ? {status:'complete', result:{status:'answered'}} : {};
  const ollama = {chat: async (packet, options) => { profiles.push(options.overview); return 'text'; }};
  await runBrowserAnalyst(api, ollama, {task:'overview'});
  await runBrowserAnalyst(api, ollama, {question:'Net sales?'});
  assert.deepEqual(profiles, [true, false]);
});

test('model timeout and disconnect abort fetches without any cloud fallback', async () => {
  const fetcher = async (url, {signal}) => new Promise((resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))));
  const client = new BrowserOllama(fetcher);
  await assert.rejects(client.request('/api/tags', null, {timeout:5}), /timed out/);
  const connection = client.connect();
  client.disconnect();
  await assert.rejects(connection, /cancelled/);
});

test('browser mediates steps and forwards only untrusted output plus server-issued step token', async () => {
  const calls = [];
  const api = async (path, payload) => {
    calls.push([path, payload]);
    if (path.endsWith('start')) return {status:'model_required', runId:'run', step:'nonce', inference};
    if (path.endsWith('step')) return {status:'complete', result:{answer:'Verified', evidence:[{rows:[[30]]}]}};
    return {status:'cancelled'};
  };
  const result = await runBrowserAnalyst(api, {chat: async () => 'untrusted text'}, {datasetId:'owned'});
  assert.equal(result.answer, 'Verified');
  assert.equal(calls[0][1].provider, 'browser_ollama');
  assert.deepEqual(calls[1], ['/api/ollama-step', {runId:'run', step:'nonce', output:'untrusted text'}]);
  assert.equal(calls[2][0], '/api/ollama-cancel');
  assert.equal(calls.some(([path]) => path === '/api/analyst'), false);
});

test('local failure cancels the run and never falls back to Groq', async () => {
  const calls = [];
  const api = async path => {
    calls.push(path);
    return {status:'model_required', runId:'run', step:'nonce', inference};
  };
  await assert.rejects(runBrowserAnalyst(api, {chat: async () => { throw Error('local failed'); }}, {}), /local failed/);
  assert.deepEqual(calls, ['/api/ollama-start', '/api/ollama-cancel']);
});

test('browser local mode is explicit and privacy notice distinguishes Render SQL from local inference', () => {
  const option = {provider:'browser_ollama', model:inference.model, available:true, label:'Local'};
  const options = answerOptions({options:[option]});
  assert.equal(chooseAnswerMode(options, '', true), '');
  assert.match(answerModeNotice(option, true, true), /inference runs on your computer.*SQL calculations.*Render/);
  assert.match(answerModeNotice(null, true, true), /browser.*Render/);
});
