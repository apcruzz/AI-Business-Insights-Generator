// Use the project's virtual environment on Windows/macOS/Linux, or system Python.
import {existsSync, readdirSync} from 'node:fs';
import {spawnSync} from 'node:child_process';
const windows = process.platform === 'win32';
const venv = windows ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const python = existsSync(venv) ? venv : windows ? 'python' : 'python3';
const commands = [
  [python, ['-B', '-m', 'tests.validate_samples']],
  [python, ['-B', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py']],
  [process.execPath, ['--test', ...readdirSync('tests').filter(name => name.endsWith('.test.mjs')).map(name => `tests/${name}`)]],
];
for (const [command, args] of commands) {
  const result = spawnSync(command, args, {stdio: 'inherit', shell: false});
  if (result.error) { console.error(`Could not start ${command}. Install the README dependencies first.`); process.exit(1); }
  if (result.status !== 0) process.exit(result.status || 1);
}
