import { prioritizeComplaints } from '@/lib/crm';
import { jsonFromTeamOrFallback } from '@/lib/team-backend';

export async function GET(request: Request) {
  const limitValue = Number(
    new URL(request.url).searchParams.get('limit') || '24',
  );
  const limit = Math.min(
    100,
    Math.max(1, Number.isFinite(limitValue) ? limitValue : 24),
  );
  const response = await jsonFromTeamOrFallback(
    `/api/crm/complaints?limit=${limit}`,
    () => prioritizeComplaints().slice(0, limit),
  );
  return Response.json(response.data, {
    headers: { 'X-CRM-Data-Source': response.source },
  });
}
