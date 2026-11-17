import test from 'node:test';
import assert from 'node:assert/strict';
import {readWorkspaceReference, writeWorkspaceReference, clearWorkspaceReference} from '../src/workspace-session.js';

test('tab storage holds only an opaque reference and can be cleared on account changes', () => {
  const values = new Map(), storage = {getItem: key => values.get(key), setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key)};
  const id = 'a'.repeat(32);
  writeWorkspaceReference(id, storage);
  assert.equal(readWorkspaceReference(storage), id);
  assert.deepEqual([...values.values()], [id]);
  writeWorkspaceReference(JSON.stringify({rows: ['private']}), storage);
  assert.equal(readWorkspaceReference(storage), id);
  clearWorkspaceReference(storage);
  assert.equal(readWorkspaceReference(storage), null);
});

test('unavailable storage does not break upload or dashboard use', () => {
  const blocked = new Proxy({}, {get() { throw Error('Storage disabled'); }});
  assert.equal(readWorkspaceReference(blocked), null);
  assert.doesNotThrow(() => writeWorkspaceReference('x'.repeat(32), blocked));
  assert.doesNotThrow(() => clearWorkspaceReference(blocked));
});
