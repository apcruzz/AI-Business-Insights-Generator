import test from 'node:test';
import assert from 'node:assert/strict';
import {answerOptions, chooseAnswerMode, answerModeNotice} from '../src/ai-options.js';

const lite = {provider: 'gemini', model: 'gemini-3.5-flash-lite', available: true, label: 'Gemini Flash-Lite'};
const flash = {...lite, model: 'gemini-3.8-flash', label: 'Gemini Flash'};
const groq = {provider: 'groq', model: 'openai/gpt-oss-120b', available: true, label: 'Groq'};
const local = {provider: 'ollama', model: 'llama3:latest', available: true, label: 'Ollama'};

test('both Gemini models are explicit choices beside all existing answer modes', () => {
  const options = answerOptions({options: [lite, flash, groq, local]});
  assert.deepEqual(options.map(option => option.value), ['', 'gemini:gemini-3.5-flash-lite', 'gemini:gemini-3.8-flash', 'groq:openai/gpt-oss-120b', 'ollama:llama3:latest']);
  assert.equal(chooseAnswerMode(options, 'gemini:gemini-3.5-flash-lite'), 'gemini:gemini-3.5-flash-lite');
  assert.equal(chooseAnswerMode(options, 'gemini:gemini-3.8-flash'), 'gemini:gemini-3.8-flash');
});

test('Gemini never becomes an automatic cloud default and refresh preserves choices', () => {
  const options = answerOptions({options: [lite, flash, groq]});
  assert.equal(chooseAnswerMode(options, '', true), '');
  assert.equal(chooseAnswerMode(options, ''), '');
  assert.equal(chooseAnswerMode(options, 'gemini:gemini-3.5-flash-lite'), 'gemini:gemini-3.5-flash-lite');
  const unavailable = answerOptions({options: [{...lite, available: false}]});
  assert.equal(chooseAnswerMode(unavailable, 'gemini:gemini-3.5-flash-lite'), '');
  assert.match(unavailable[1].label, /API key required/);
});

test('Gemini sharing is explained at the existing answer-mode control', () => {
  const notice = answerModeNotice(lite, true);
  assert.match(notice, /selecting this mode generates an initial overview in Business assistant/);
  assert.match(notice, /sample values.*calculation results.*sent to Google/);
  assert.match(notice, /current filters/);
  assert.match(notice, /completed overviews are reused/);
  assert.match(answerModeNotice(null, true, false, true), /Gemini is available/);
});

test('Gemini availability does not alter Groq and browser-local sharing notices', () => {
  assert.match(answerModeNotice(groq, true, false, true), /sent to Groq/);
  assert.doesNotMatch(answerModeNotice(groq, true, false, true), /sent to Google/);
  assert.match(answerModeNotice({provider: 'browser_ollama'}, false, true, true), /inference runs on your computer/);
  assert.match(answerModeNotice({provider: 'browser_ollama'}, false, true, true), /No AI inference requests go to cloud providers/);
});
