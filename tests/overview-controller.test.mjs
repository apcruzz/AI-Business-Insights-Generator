import test from 'node:test';
import assert from 'node:assert/strict';
import {OverviewController, overviewScopeKey} from '../src/overview-controller.js';
import {answerOptions, answerModeNotice, chooseAnswerMode} from '../src/ai-options.js';

const scope = {datasetId: 'dataset-a', provider: 'gemini', model: 'gemini-3.8-flash', filters: {product: 'Tea'}};
const answer = {status: 'answered', answer: 'Review Tea.', conversationId: 'overview-a'};
const tick = () => new Promise(resolve => setImmediate(resolve));
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return {promise, resolve, reject}; };
function controller(request, options = {}) {
  const states = [];
  const value = new OverviewController({request, onChange: state => states.push(state), delay: 10000, ...options});
  return {value, states};
}

test('Gemini is explicit, preserves other providers, and explains cloud sharing', () => {
  const gemini = {provider: 'gemini', model: scope.model, available: true, label: 'Gemini'};
  const groq = {provider: 'groq', model: 'openai/gpt-oss-120b', available: true, label: 'Groq'};
  const options = answerOptions({options: [gemini, groq]});
  assert.equal(chooseAnswerMode(options, '', true), '');
  assert.equal(chooseAnswerMode(options, `gemini:${scope.model}`), `gemini:${scope.model}`);
  assert.equal(options.length, 3);
  assert.match(answerModeNotice(gemini, true), /initial overview.*sample values.*sent to Google/);
  assert.match(answerModeNotice(null, true, false, true), /Gemini is available/);
  const unavailable = answerOptions({options: [{...gemini, available: false}]});
  assert.equal(chooseAnswerMode(unavailable, `gemini:${scope.model}`), '');
  assert.match(unavailable[1].label, /API key required/);
});

test('scope uses dataset, provider, model and all filters; object order is irrelevant', () => {
  const key = overviewScopeKey(scope);
  assert.equal(key, overviewScopeKey({...scope, filters: {from: '', product: 'Tea'}}));
  for (const change of [{datasetId: 'other'}, {provider: 'groq'}, {model: 'other'}, ...['from', 'to', 'category', 'product', 'weekday', 'period'].map(id => ({filters: {...scope.filters, [id]: 'different'}}))]) {
    assert.notEqual(key, overviewScopeKey({...scope, ...change}));
  }
  assert.equal(overviewScopeKey(null), '');
  assert.equal(overviewScopeKey({...scope, datasetId: ''}), '');
});

test('calculated mode and a missing dataset do not request AI', async () => {
  let calls = 0;
  const {value} = controller(() => { calls++; });
  value.select(null);
  value.select({...scope, datasetId: ''});
  await value.start();
  assert.equal(calls, 0);
  assert.equal(value.state.status, 'idle');
});

test('local Ollama overviews share scoped deduplication and explicit local privacy notices', async () => {
  for (const provider of ['ollama', 'browser_ollama']) {
    let calls = 0;
    const local = {...scope, provider, model: 'llama3.2:3b'};
    const {value} = controller(async payload => {
      calls++;
      assert.equal(payload.provider, provider);
      assert.equal(payload.task, 'overview');
      return answer;
    });
    value.select(local); await value.start();
    value.select({...local});
    assert.equal(calls, 1);
    assert.equal(value.state.status, 'ready');
    assert.match(answerModeNotice(local, false, true), /automatic overview/);
    value.dispose();
  }
});

test('repeated renders, model refresh and navigation deduplicate one pending request', async () => {
  const pending = deferred(); let calls = 0;
  const {value} = controller((payload, signal) => {
    calls++; assert.equal(payload.task, 'overview'); assert.ok(signal instanceof AbortSignal); return pending.promise;
  });
  value.select(scope);
  const running = value.start();
  value.select({...scope, filters: {...scope.filters}});
  value.select(scope);
  assert.equal(calls, 1);
  pending.resolve(answer);
  await running;
  assert.equal(value.state.status, 'ready');
  value.select(scope);
  assert.equal(calls, 1);
});

test('a changed selection aborts and ignores a late successful answer', async () => {
  const first = deferred(); let signal;
  const {value} = controller((_scope, requestSignal) => { signal = requestSignal; return first.promise; });
  value.select(scope);
  const running = value.start();
  value.select({...scope, filters: {product: 'Coffee'}});
  assert.equal(signal.aborted, true);
  first.resolve(answer);
  await running;
  assert.equal(value.state.status, 'scheduled');
  assert.equal(value.cache.size, 0);
  value.select(null);
});

test('changing to calculated mode also ignores late failures', async () => {
  const pending = deferred();
  const {value} = controller(() => pending.promise);
  value.select(scope);
  const running = value.start();
  value.select(null);
  pending.reject(Error('stale error'));
  await running;
  assert.equal(value.state.status, 'idle');
  assert.equal(value.cache.size, 0);
});

test('completed overviews are reused on return to the same selection', async () => {
  let calls = 0;
  const {value} = controller(async () => { calls++; return answer; });
  value.select(scope); await value.start();
  value.select({...scope, filters: {product: 'Coffee'}}); await value.start();
  value.select(scope);
  assert.equal(value.state.response.conversationId, 'overview-a');
  assert.equal(calls, 2);
});

test('failed or unverified overviews stay explicit and require a retry', async () => {
  let calls = 0;
  const {value} = controller(async () => {
    if (++calls === 1) throw Error('Gemini quota reached.');
    return answer;
  });
  value.select(scope); await value.start();
  assert.equal(value.state.status, 'error');
  assert.match(value.state.error, /quota/);
  value.select(scope); await tick();
  assert.equal(calls, 1);
  await value.retry();
  assert.equal(calls, 2);
  assert.equal(value.state.status, 'ready');
  const failed = controller(async () => ({status: 'incomplete', answer: 'Could not verify.', evidence: []})).value;
  failed.select(scope); await failed.start();
  assert.equal(failed.state.status, 'error');
});

test('rapid filter changes are debounced before calling a provider', async () => {
  let calls = 0;
  const {value} = controller(async payload => { calls++; assert.equal(payload.filters.product, 'Coffee'); return answer; }, {delay: 5});
  value.select(scope);
  value.select({...scope, filters: {product: 'Coffee'}});
  await new Promise(resolve => setTimeout(resolve, 25));
  assert.equal(calls, 1);
});

test('cache bounds and expiry prevent indefinite session memory growth', async () => {
  let calls = 0;
  const {value} = controller(async () => { calls++; return answer; }, {maxEntries: 1, ttl: 1});
  value.select(scope); await value.start();
  value.select({...scope, datasetId: 'dataset-b'}); await value.start();
  assert.equal(value.cache.size, 1);
  value.select(scope); await value.start();
  assert.equal(calls, 3);
  value.select(null);
  await new Promise(resolve => setTimeout(resolve, 5));
  value.select(scope); await value.start();
  assert.equal(calls, 4);
});

test('unmount cancels a scheduled overview without starting a provider request', async () => {
  let calls = 0;
  const {value, states} = controller(async () => { calls++; return answer; }, {delay: 5});
  value.select(scope);
  value.dispose();
  const count = states.length;
  await new Promise(resolve => setTimeout(resolve, 25));
  value.select(scope);
  await value.retry();
  await value.start();
  assert.equal(calls, 0);
  assert.equal(states.length, count);
  assert.equal(value.state.status, 'idle');
});

test('unmount aborts an in-flight overview and suppresses late account data', async () => {
  const pending = deferred(); let signal;
  const {value, states} = controller((_payload, requestSignal) => { signal = requestSignal; return pending.promise; });
  value.select(scope);
  const running = value.start();
  value.dispose();
  const count = states.length;
  pending.resolve(answer);
  await running;
  assert.equal(signal.aborted, true);
  assert.equal(value.scope, null);
  assert.equal(value.cache.size, 0);
  assert.equal(states.length, count);
  assert.equal(value.state.status, 'idle');
});

test('unmount clears cached overviews and ignores late failures', async () => {
  const pending = deferred();
  const {value, states} = controller(async payload => payload.datasetId === scope.datasetId ? answer : pending.promise);
  value.select(scope); await value.start();
  assert.equal(value.cache.size, 1);
  value.select({...scope, datasetId: 'other'});
  const running = value.start();
  value.dispose();
  const count = states.length;
  pending.reject(Error('late failure'));
  await running;
  assert.equal(value.cache.size, 0);
  assert.equal(states.length, count);
});
