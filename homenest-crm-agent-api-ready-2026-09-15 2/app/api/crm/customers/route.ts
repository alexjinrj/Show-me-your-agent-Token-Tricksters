import { rateCustomers } from '@/lib/crm';
import { jsonFromTeamOrFallback } from '@/lib/team-backend';

export async function GET() {
  const response = await jsonFromTeamOrFallback(
    '/api/crm/customers',
    rateCustomers,
  );
  return Response.json(response.data, {
    headers: { 'X-CRM-Data-Source': response.source },
  });
}
