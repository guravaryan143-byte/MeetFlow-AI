import { randomUUID } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

const frontendDir = path.dirname(fileURLToPath(import.meta.url));
const projectDir = path.resolve(frontendDir, '..');
const backendDir = path.join(projectDir, 'backend');
const runId = randomUUID();
const databaseFile = path.join(os.tmpdir(), `meetflow-e2e-${runId}.db`);
const uploadDir = path.join(os.tmpdir(), `meetflow-e2e-uploads-${runId}`);
mkdirSync(uploadDir, { recursive: true });

process.env.MEETFLOW_E2E_DB = databaseFile;
process.env.MEETFLOW_E2E_UPLOADS = uploadDir;

const databaseUrl = `sqlite:///${databaseFile.replace(/\\/g, '/')}`;
const backendEnv = {
  ...process.env,
  ENVIRONMENT: 'development',
  DATABASE_URL: databaseUrl,
  UPLOAD_DIR: uploadDir,
  CORS_ORIGINS: 'http://127.0.0.1:5174',
  INTEGRATION_MODE: 'mock',
  AI_PROVIDER: 'deterministic',
};

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 45_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  globalTeardown: './tests/e2e/global-teardown.ts',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: 'http://127.0.0.1:5174',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: 'python -m uvicorn app.main:app --host 127.0.0.1 --port 8001',
      cwd: backendDir,
      url: 'http://127.0.0.1:8001/health',
      env: backendEnv,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5174 --strictPort',
      cwd: frontendDir,
      url: 'http://127.0.0.1:5174',
      env: {
        ...process.env,
        VITE_API_BASE_URL: 'http://127.0.0.1:8001',
      },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
