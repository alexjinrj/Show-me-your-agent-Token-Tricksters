import type { PrioritizedComplaint, RatedCustomer } from './crm.ts';

export type CrmSummary = {
  customerCount: number;
  complaintCount: number;
  highRiskCustomers: number;
  overdueComplaints: number;
  unrespondedComplaints: number;
  aTierCustomers: number;
};

export type IntegrationStatus = {
  connected: boolean;
  mode: 'team-backend' | 'local-demo';
  message: string;
};

export type ResolutionProposalInput = {
  complaintId: string;
  resolutionId: 'refund' | 'reship' | 'credit' | 'monitor';
  replyDraft?: string;
  internalDraft?: string;
};

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body = (await response.json().catch(() => null)) as
    | (T & { error?: string })
    | null;
  if (!response.ok) {
    throw new Error(body?.error || `CRM API returned ${response.status}.`);
  }
  return body as T;
}

export const crmApi = {
  status: () => jsonRequest<IntegrationStatus>('/api/integration/status'),
  summary: () => jsonRequest<CrmSummary>('/api/crm/summary'),
  customers: () => jsonRequest<RatedCustomer[]>('/api/crm/customers'),
  customer: (customerId: string) =>
    jsonRequest<RatedCustomer & { complaints: PrioritizedComplaint[] }>(
      `/api/crm/customers/${encodeURIComponent(customerId)}`,
    ),
  complaints: (limit = 24) =>
    jsonRequest<PrioritizedComplaint[]>(
      `/api/crm/complaints?limit=${encodeURIComponent(limit)}`,
    ),
  complaint: (complaintId: string) =>
    jsonRequest<PrioritizedComplaint>(
      `/api/crm/complaints/${encodeURIComponent(complaintId)}`,
    ),
  submitProposal: (proposal: ResolutionProposalInput) =>
    jsonRequest<{ id: string; status: string }>('/api/crm/proposals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(proposal),
    }),
  askAgent: (question: string) =>
    jsonRequest<{
      answer: string;
      mode: 'llm' | 'demo';
      toolCalls: Array<{
        name: string;
        arguments: Record<string, unknown>;
        resultSummary: string;
      }>;
    }>('/api/agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }),
};
