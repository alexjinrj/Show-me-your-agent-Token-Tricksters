import { prioritizeComplaints, rateCustomers } from '@/lib/crm';
import { jsonFromTeamOrFallback } from '@/lib/team-backend';

type RouteContext = { params: Promise<{ customerId: string }> };

export async function GET(_request: Request, context: RouteContext) {
  const { customerId } = await context.params;
  const id = customerId.toUpperCase();
  const response = await jsonFromTeamOrFallback(
    `/api/crm/customers/${encodeURIComponent(id)}`,
    () => {
      const customer = rateCustomers().find((item) => item.id === id);
      if (!customer) return null;
      return {
        ...customer,
        complaints: prioritizeComplaints().filter(
          (ticket) => ticket.customerId === id,
        ),
      };
    },
  );
  if (!response.data)
    return Response.json({ error: 'CRM customer not found.' }, { status: 404 });
  return Response.json(response.data, {
    headers: { 'X-CRM-Data-Source': response.source },
  });
}
