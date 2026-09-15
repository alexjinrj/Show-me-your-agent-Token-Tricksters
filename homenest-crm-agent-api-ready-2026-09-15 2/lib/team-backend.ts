import { runCrmTool } from './agent.ts';

export type ToolExecution = {
  result: unknown;
  source: 'team-backend' | 'local-demo';
};

const configuredBaseUrl = () =>
  (process.env.TEAM_API_BASE_URL || '').trim().replace(/\/$/, '');

const timeoutMs = () => {
  const configured = Number(process.env.TEAM_API_TIMEOUT_MS || '3000');
  return Number.isFinite(configured) && configured > 0 ? configured : 3000;
};

export function teamBackendConfigured() {
  return Boolean(configuredBaseUrl());
}

export async function requestTeamBackend(
  path: string,
  init: RequestInit = {},
): Promise<Response | null> {
  const baseUrl = configuredBaseUrl();
  if (!baseUrl) return null;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs());
  const headers = new Headers(init.headers);
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');
  if (init.body && !headers.has('Content-Type'))
    headers.set('Content-Type', 'application/json');
  try {
    return await fetch(`${baseUrl}${path}`, {
      ...init,
      headers,
      cache: 'no-store',
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

export async function jsonFromTeamOrFallback(
  path: string,
  fallback: () => unknown,
): Promise<{ data: unknown; source: 'team-backend' | 'local-demo' }> {
  try {
    const response = await requestTeamBackend(path);
    if (response?.ok) {
      return { data: await response.json(), source: 'team-backend' };
    }
  } catch {
    // The standalone demo remains available when the team API is offline.
  }
  return { data: fallback(), source: 'local-demo' };
}

const idArgument = (value: unknown) =>
  typeof value === 'string' ? encodeURIComponent(value.toUpperCase()) : '';

export async function runCrmToolWithBackend(
  name: string,
  args: Record<string, unknown>,
): Promise<ToolExecution> {
  const mapping: Record<string, string | undefined> = {
    list_priority_complaints: '/api/crm/complaints?limit=10',
    get_customer_360: args.customer_id
      ? `/api/crm/customers/${idArgument(args.customer_id)}`
      : undefined,
    get_complaint_detail: args.complaint_id
      ? `/api/crm/complaints/${idArgument(args.complaint_id)}`
      : undefined,
  };
  const path = mapping[name];
  if (path) {
    const response = await requestTeamBackend(path).catch(() => null);
    if (response?.ok) {
      return { result: await response.json(), source: 'team-backend' };
    }
  }
  return { result: runCrmTool(name, args), source: 'local-demo' };
}
