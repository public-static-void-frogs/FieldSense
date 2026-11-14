import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { after } from 'node:test';

// Exercise the real API using a temporary database and explicit test-only inputs.
const directory = fileURLToPath(new URL('../../../backend', import.meta.url));
// Reuse the contract stand-in for deterministic frontend HTTP tests.
const provider = spawn(process.execPath, [`${directory}/postman/mocks/open-meteo/default.js`], {
  env: { ...process.env, PORT: '0', WEATHER_TEST_LOG_PORT: '1' },
  stdio: ['ignore', 'pipe', 'pipe'],
});
const providerPort = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => {
    provider.kill();
    reject(new Error('Weather test provider startup timed out'));
  }, 10000);
  provider.once('error', reject);
  provider.once('exit', (code) => {
    clearTimeout(timer);
    reject(new Error(`Weather test provider exited (${code})`));
  });
  provider.stdout.on('data', (data) => {
    const match = String(data).match(/READY_UPSTREAM_PORT=(\d+)/);
    if (match) {
      clearTimeout(timer);
      resolve(match[1]);
    }
  });
});
after(() => provider.kill());
const virtualenv = `${directory}/.venv/bin/python`;
const python = process.env.NASA_BACKEND_PYTHON ?? (existsSync(virtualenv) ? virtualenv : 'python3');
const databaseDirectory = await mkdtemp(join(tmpdir(), 'nasa-api-test-'));
const server = spawn(
  python,
  [
    '-u',
    '-c',
    `
import socket
import uvicorn
from alembic import command
from alembic.config import Config
command.upgrade(Config('alembic.ini'), 'head')
sock = socket.socket()
sock.bind(('127.0.0.1', 0))
sock.listen(128)
print(f'READY_PORT={sock.getsockname()[1]}', flush=True)
uvicorn.Server(uvicorn.Config('app.main:app', log_level='error')).run(sockets=[sock])
`,
  ],
  {
    cwd: directory,
    env: {
      ...process.env,
      DATABASE_URL: `sqlite:///${databaseDirectory}/test.db`,
      JWT_SECRET: 'frontend-test-signing-key-with-at-least-32-bytes',
      JWT_ISSUER: 'frontend-test-fieldshift',
      COOKIE_SECURE: 'false',
      WEATHER_FORECAST_URL: `http://127.0.0.1:${providerPort}/v1/forecast`,
      WEATHER_ARCHIVE_URL: `http://127.0.0.1:${providerPort}/v1/archive`,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  },
);
let errors = '';
server.stderr.on('data', (data) => {
  errors += data;
});
const nativeFetch = globalThis.fetch;
const originalApiUrl = process.env.VITE_API_BASE_URL;
let baseUrl;
try {
  const port = await new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error(`Backend startup timed out. ${errors}`)),
      10000,
    );
    server.once('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
    server.once('exit', (code) => {
      clearTimeout(timer);
      reject(new Error(`Backend exited (${code}). Install backend requirements. ${errors}`));
    });
    server.stdout.on('data', (data) => {
      const match = String(data).match(/READY_PORT=(\d+)/);
      if (match) {
        clearTimeout(timer);
        resolve(match[1]);
      }
    });
  });
  baseUrl = `http://127.0.0.1:${port}`;
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      const response = await nativeFetch(baseUrl);
      if (response.ok) {
        break;
      }
    } catch {
      /* Wait for uvicorn to finish loading the application. */
    }
    if (attempt === 99) {
      throw new Error(`Backend is unavailable. ${errors}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
} catch (error) {
  server.kill();
  throw error;
}
process.env.VITE_API_BASE_URL = `${baseUrl}/api/v1`;
// Node has no browser cookie jar. Preserve the real HttpOnly cookie in this test transport.
const registration = await nativeFetch(`${baseUrl}/api/v1/auth/register`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    email: 'frontend-test@example.com',
    fullName: 'Frontend Test',
    password: 'Test-password-123',
    farmName: 'Test farm',
    latitude: 50.4501,
    longitude: 30.5234,
  }),
});
if (registration.status !== 201) {
  server.kill();
  throw new Error(`Test account registration failed: ${await registration.text()}`);
}
let cookie = registration.headers.get('set-cookie').split(';')[0];
const fieldInput = JSON.parse(await readFile(`${directory}/tests/field_input.json`, 'utf8'));
export const testFields = [];
for (const [name, crop] of [
  ['Test North', 'Winter wheat'],
  ['Test South', 'Corn'],
]) {
  const response = await nativeFetch(`${baseUrl}/api/v1/fields`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Cookie: cookie },
    body: JSON.stringify({ ...fieldInput, name, crop }),
  });
  if (response.status !== 201) {
    throw new Error(`Test field setup failed: ${await response.text()}`);
  }
  testFields.push(await response.json());
}

globalThis.fetch = async (input, init = {}) => {
  const headers = new Headers(init.headers);
  if (String(input).startsWith(baseUrl)) {
    headers.set('Cookie', cookie);
  }
  const response = await nativeFetch(input, { ...init, headers });
  const nextCookie = response.headers.get('set-cookie');
  if (nextCookie && String(input).startsWith(baseUrl)) {
    cookie = nextCookie.split(';')[0];
  }
  return response;
};
after(async () => {
  globalThis.fetch = nativeFetch;
  if (originalApiUrl === undefined) {
    delete process.env.VITE_API_BASE_URL;
  } else {
    process.env.VITE_API_BASE_URL = originalApiUrl;
  }
  server.kill();
  await new Promise((resolve) => server.once('exit', resolve));
  await rm(databaseDirectory, { recursive: true, force: true });
});
