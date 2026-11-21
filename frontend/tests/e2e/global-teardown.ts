import { rm } from 'node:fs/promises';
import type { FullConfig } from '@playwright/test';

export default async function globalTeardown(_config: FullConfig) {
  const paths = [process.env.MEETFLOW_E2E_DB, process.env.MEETFLOW_E2E_UPLOADS].filter(
    (value): value is string => Boolean(value),
  );
  await Promise.all(paths.map((target) => rm(target, { recursive: true, force: true })));
}
