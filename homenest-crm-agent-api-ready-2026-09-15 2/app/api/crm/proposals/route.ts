import { requestTeamBackend, teamBackendConfigured } from '@/lib/team-backend';

export async function POST(request: Request) {
  if (!teamBackendConfigured()) {
    return Response.json(
      {
        error: 'The team backend is not configured.',
        effect:
          'No proposal was persisted and no business action was executed.',
      },
      { status: 503 },
    );
  }
  try {
    const body = await request.text();
    const response = await requestTeamBackend('/api/crm/proposals', {
      method: 'POST',
      body,
    });
    if (!response) throw new Error('The team backend returned no response.');
    return new Response(await response.text(), {
      status: response.status,
      headers: { 'Content-Type': 'application/json' },
    });
  } catch {
    return Response.json(
      {
        error: 'The team backend is currently unreachable.',
        effect:
          'No proposal was persisted and no business action was executed.',
      },
      { status: 502 },
    );
  }
}
