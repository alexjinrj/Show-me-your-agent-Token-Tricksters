import { prioritizeComplaints } from '@/lib/crm';
import { jsonFromTeamOrFallback } from '@/lib/team-backend';

type RouteContext = { params: Promise<{ complaintId: string }> };

export async function GET(_request: Request, context: RouteContext) {
  const { complaintId } = await context.params;
  const id = complaintId.toUpperCase();
  const response = await jsonFromTeamOrFallback(
    `/api/crm/complaints/${encodeURIComponent(id)}`,
    () => prioritizeComplaints().find((item) => item.id === id) || null,
  );
  if (!response.data)
    return Response.json(
      { error: 'CRM complaint not found.' },
      { status: 404 },
    );
  return Response.json(response.data, {
    headers: { 'X-CRM-Data-Source': response.source },
  });
}
