import { requestTeamBackend, teamBackendConfigured } from '@/lib/team-backend';

export async function GET() {
  if (!teamBackendConfigured()) {
    return Response.json({
      connected: false,
      mode: 'local-demo',
      message: 'TEAM_API_BASE_URL is not configured.',
    });
  }

  try {
    const response = await requestTeamBackend('/healthz');
    return Response.json({
      connected: Boolean(response?.ok),
      mode: response?.ok ? 'team-backend' : 'local-demo',
      message: response?.ok
        ? 'Team FastAPI is reachable.'
        : `Team FastAPI health check returned ${response?.status || 'no response'}.`,
    });
  } catch {
    return Response.json({
      connected: false,
      mode: 'local-demo',
      message: 'Team FastAPI is configured but currently unreachable.',
    });
  }
}
