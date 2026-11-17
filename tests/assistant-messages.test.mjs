import test from 'node:test';
import assert from 'node:assert/strict';
import {assistantMessages, formatAIAnswer} from '../src/assistant-messages.js';

const response = {mode: 'Gemini cloud data analyst', model: 'gemini-3.5-flash-lite',
  answer: 'Net sales are 70.', evidence: [{columns: ['net_sales'], rows: [[70]]}]};
const ready = {status: 'ready', response};

test('an automatic overview is exactly one assistant message without an invented user question', () => {
  const messages = assistantMessages(ready);
  assert.equal(messages.length, 1);
  assert.equal(messages[0].role, 'assistant');
  assert.match(messages[0].content, /^Automatic overview\n/);
  assert.match(messages[0].content, /Net sales are 70/);
  assert.equal(messages.some(item => item.role === 'user'), false);
});

test('scheduled and loading states occupy the same assistant message', () => {
  for (const status of ['scheduled', 'loading']) {
    const messages = assistantMessages({status});
    assert.equal(messages.length, 1);
    assert.equal(messages[0].role, 'assistant');
    assert.equal(messages[0].status, 'pending');
    assert.doesNotMatch(messages[0].content, /Net sales are 70/);
  }
});

test('follow-up questions retain the overview once and preserve the real speakers', () => {
  const turns = [{question: 'What supports that?', answer: 'Coffee leads recorded sales.'}];
  const pending = {question: 'What next?', answer: 'Inspecting data…', status: 'pending'};
  const copy = JSON.stringify(turns);
  for (let i = 0; i < 3; i++) {
    const messages = assistantMessages(ready, turns, pending);
    assert.deepEqual(messages.map(item => item.role), ['assistant', 'user', 'assistant', 'user', 'assistant']);
    assert.equal(messages.filter(item => item.content.startsWith('Automatic overview')).length, 1);
    assert.equal(messages[1].content, 'What supports that?');
    assert.equal(messages.at(-1).status, 'pending');
  }
  assert.equal(JSON.stringify(turns), copy);
});

test('a failed overview remains explicit while manual questions can still be answered', () => {
  const messages = assistantMessages({status: 'error', error: 'Gemini unavailable (HTTP 503).'},
    [{question: 'Can you calculate the total?', answer: 'The recorded total is 70.'}]);
  assert.equal(messages[0].status, 'error');
  assert.match(messages[0].content, /HTTP 503/);
  assert.match(messages[0].content, /New conversation to retry/);
  assert.deepEqual(messages.map(item => item.role), ['assistant', 'user', 'assistant']);
});

test('calculated and other provider conversations keep their existing speaker order', () => {
  assert.deepEqual(assistantMessages({status: 'idle'}), []);
  const messages = assistantMessages({status: 'idle'}, [{question: 'Total?', answer: 'Calculated answer\n70'}]);
  assert.deepEqual(messages.map(item => item.role), ['user', 'assistant']);
  assert.equal(messages[1].content, 'Calculated answer\n70');
});

test('model text stays message text and calculation notes depend on actual evidence', () => {
  const literal = '<script>unsafe()</script>';
  const messages = assistantMessages({status: 'ready', response: {...response, answer: literal}});
  assert.equal(messages[0].content.includes(literal), true);
  assert.match(formatAIAnswer(response), /supporting calculations/);
  assert.doesNotMatch(formatAIAnswer({...response, evidence: []}), /supporting calculations/);
});
