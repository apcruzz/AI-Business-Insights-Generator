import test from 'node:test';
import assert from 'node:assert/strict';
import {answerOptions, chooseAnswerMode, answerModeNotice} from '../src/ai-options.js';

const groq = {provider: 'groq', model: 'openai/gpt-oss-120b', label: 'GPT-OSS 120B · Groq (cloud)', available: true};
const local = {provider: 'ollama', model: 'llama3:latest', label: 'Llama 3', available: true};

test('cloud requires explicit selection, including when it is the only available AI', () => {
  const options = answerOptions({options: [groq]});
  assert.equal(chooseAnswerMode(options, '', true), '');
  assert.equal(chooseAnswerMode(options, options[1].value), options[1].value);
  assert.equal(chooseAnswerMode(answerOptions({options: [local, groq]}), '', true), 'ollama:llama3:latest');
});

test('refresh preserves calculated mode and removes unavailable choices', () => {
  const options = answerOptions({options: [local, {...groq, available: false}]});
  assert.equal(chooseAnswerMode(options, ''), '');
  assert.equal(chooseAnswerMode(options, 'groq:openai/gpt-oss-120b'), '');
  assert.equal(options[2].available, false);
  assert.match(options[2].label, /API key required/);
});

test('data notice distinguishes cloud transfer from local analysis', () => {
  assert.match(answerModeNotice(groq, true), /sample values.*calculation results.*sent to Groq/);
  assert.match(answerModeNotice(local, false), /on this computer/);
  assert.match(answerModeNotice(null, false), /backend API key/);
});
