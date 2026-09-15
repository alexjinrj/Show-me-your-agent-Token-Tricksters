import { dashboard } from '@/lib/crm';
import { jsonFromTeamOrFallback } from '@/lib/team-backend';

export async function GET() {
  const response = await jsonFromTeamOrFallback('/api/crm/summary', () => {
    const data = dashboard();
    return {
      customerCount: data.customers.length,
      complaintCount: data.complaints.length,
      highRiskCustomers: data.highRiskCustomers,
      overdueComplaints: data.overdueComplaints,
      unrespondedComplaints: data.unrespondedComplaints,
      aTierCustomers: data.aTierCustomers,
    };
  });
  return Response.json(response.data, {
    headers: { 'X-CRM-Data-Source': response.source },
  });
}
