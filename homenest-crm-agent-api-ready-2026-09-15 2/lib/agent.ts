import { dashboard, prioritizeComplaints, rateCustomers } from './crm.ts';
import {
  compareResolutionOptions,
  estimateFinancialImpact,
  getInventoryAvailability,
  getOrderTimeline,
  investigateComplaint,
} from './resolution.ts';

export type AgentToolCall = {
  name: string;
  arguments: Record<string, unknown>;
  resultSummary: string;
};

const idSchema = (description: string) => ({
  type: 'object',
  properties: { complaint_id: { type: 'string', description } },
  required: ['complaint_id'],
  additionalProperties: false,
});

export const crmTools = [
  {
    type: 'function',
    name: 'list_priority_complaints',
    description: 'List open complaints by deterministic service priority.',
    strict: true,
    parameters: {
      type: 'object',
      properties: {},
      required: [],
      additionalProperties: false,
    },
  },
  {
    type: 'function',
    name: 'get_customer_360',
    description:
      'Get customer value, relationship risk, source facts and linked complaints.',
    strict: true,
    parameters: {
      type: 'object',
      properties: {
        customer_id: {
          type: 'string',
          description: 'Customer ID, for example CUS-004',
        },
      },
      required: ['customer_id'],
      additionalProperties: false,
    },
  },
  {
    type: 'function',
    name: 'get_complaint_detail',
    description:
      'Get complaint SLA, response status, priority evidence and owner.',
    strict: true,
    parameters: idSchema('Complaint ID, for example TKT-004'),
  },
  {
    type: 'function',
    name: 'get_order_timeline',
    description:
      'Investigate purchase, promised delivery, actual delivery, complaint and SLA events.',
    strict: true,
    parameters: idSchema('Complaint ID'),
  },
  {
    type: 'function',
    name: 'get_inventory_availability',
    description:
      'Check demo replacement stock and replenishment time. Values are assumptions.',
    strict: true,
    parameters: idSchema('Complaint ID'),
  },
  {
    type: 'function',
    name: 'estimate_refund_impact',
    description:
      'Estimate refund, replacement and service-credit financial impact in BRL.',
    strict: true,
    parameters: idSchema('Complaint ID'),
  },
  {
    type: 'function',
    name: 'compare_resolution_options',
    description:
      'Compare refund, replacement, credit and monitor options by cost, time and recovery.',
    strict: true,
    parameters: idSchema('Complaint ID'),
  },
  {
    type: 'function',
    name: 'recommend_resolution',
    description:
      'Run a cross-functional investigation and return one recommended resolution.',
    strict: true,
    parameters: idSchema('Complaint ID'),
  },
  {
    type: 'function',
    name: 'draft_customer_reply',
    description:
      'Create an unsent reply draft grounded in verified complaint facts.',
    strict: true,
    parameters: {
      type: 'object',
      properties: {
        complaint_id: { type: 'string', description: 'Complaint ID' },
        tone: { type: 'string', enum: ['professional', 'empathetic'] },
      },
      required: ['complaint_id', 'tone'],
      additionalProperties: false,
    },
  },
  {
    type: 'function',
    name: 'create_followup_proposal',
    description:
      'Create a proposed action for human approval. Does not execute it.',
    strict: true,
    parameters: {
      type: 'object',
      properties: {
        complaint_id: { type: 'string', description: 'Complaint ID' },
        resolution_id: {
          type: 'string',
          enum: ['refund', 'reship', 'credit', 'monitor'],
        },
      },
      required: ['complaint_id', 'resolution_id'],
      additionalProperties: false,
    },
  },
] as const;

const compactComplaint = (
  ticket: ReturnType<typeof prioritizeComplaints>[number],
) => ({
  complaintId: ticket.id,
  customerId: ticket.customerId,
  customerName: ticket.customer.name,
  orderId: ticket.orderId,
  sourceOrderId: ticket.sourceOrderId,
  issue: ticket.issue,
  reviewScore: ticket.reviewScore,
  reviewText: ticket.reviewText,
  lateDays: ticket.lateDays,
  status: ticket.status,
  priorityScore: ticket.priorityScore,
  priorityLevel: ticket.priorityLevel,
  overdueHours: ticket.overdueHours,
  hasFirstResponse: Boolean(ticket.firstResponseAt),
  customerValueTier: ticket.customer.valueTier,
  relationshipRisk: ticket.customer.riskLevel,
  reasons: ticket.reasons,
  nextAction: ticket.nextAction,
  ownerRole: ticket.ownerRole,
});

const idArgument = (value: unknown) =>
  typeof value === 'string' ? value.toUpperCase() : '';
const complaint = (args: Record<string, unknown>) =>
  prioritizeComplaints().find(
    (item) => item.id === idArgument(args.complaint_id),
  );

export function runCrmTool(
  name: string,
  args: Record<string, unknown>,
): unknown {
  const complaints = prioritizeComplaints();
  if (name === 'list_priority_complaints')
    return complaints.slice(0, 10).map(compactComplaint);
  if (name === 'get_customer_360') {
    const id = idArgument(args.customer_id);
    const customer = rateCustomers().find((item) => item.id === id);
    if (!customer) return { error: `Customer ${id} was not found.` };
    return {
      ...customer,
      complaints: complaints
        .filter((ticket) => ticket.customerId === id)
        .map(compactComplaint),
      boundary:
        'Value uses Olist payment, frequency and recency. Risk uses Olist review/delivery signals plus labelled CRM replay fields. This is not a credit rating.',
    };
  }
  const ticket = complaint(args);
  if (!ticket)
    return {
      error: `Complaint ${idArgument(args.complaint_id)} was not found.`,
    };
  if (name === 'get_complaint_detail') return compactComplaint(ticket);
  if (name === 'get_order_timeline') return getOrderTimeline(ticket.id);
  if (name === 'get_inventory_availability')
    return getInventoryAvailability(ticket.id);
  if (name === 'estimate_refund_impact')
    return estimateFinancialImpact(ticket.id);
  if (name === 'compare_resolution_options')
    return compareResolutionOptions(ticket.id);
  if (name === 'recommend_resolution') return investigateComplaint(ticket.id);
  if (name === 'draft_customer_reply') {
    const prefix =
      args.tone === 'empathetic'
        ? 'Hello, we are sorry that this experience has taken so long to resolve.'
        : 'Hello, we have received your service request.';
    return {
      complaintId: ticket.id,
      status: 'Unsent draft',
      draft: `${prefix} We are reviewing order ${ticket.orderId}, including its delivery timeline. A team member will verify the proposed resolution before confirming the next step.`,
      verifiedFacts: compactComplaint(ticket),
    };
  }
  if (name === 'create_followup_proposal') {
    const options = compareResolutionOptions(ticket.id);
    const selected = options.find((option) => option.id === args.resolution_id);
    if (!selected)
      return {
        error: `Resolution ${String(args.resolution_id)} is not available.`,
      };
    return {
      complaintId: ticket.id,
      status: 'Pending Review',
      resolution: selected,
      owner: ticket.ownerRole,
      dueAt: ticket.dueAt,
      effect:
        'No message was sent and no order, refund or inventory record was changed.',
    };
  }
  return { error: `Unknown tool ${name}.` };
}

function summarizeResult(name: string, result: unknown) {
  if (Array.isArray(result)) return `Returned ${result.length} record(s)`;
  if (result && typeof result === 'object' && 'error' in result)
    return String((result as { error: unknown }).error);
  return name === 'draft_customer_reply'
    ? 'Created one unsent draft'
    : 'Returned one grounded result';
}

function execute(
  name: string,
  args: Record<string, unknown>,
  calls: AgentToolCall[],
) {
  const result = runCrmTool(name, args);
  calls.push({
    name,
    arguments: args,
    resultSummary: summarizeResult(name, result),
  });
  return result;
}

export function demoAgentAnswer(question: string) {
  const ticketId = question.toUpperCase().match(/TKT-\d{3}/)?.[0];
  const customerId = question.toUpperCase().match(/CUS-\d{3}/)?.[0];
  const toolCalls: AgentToolCall[] = [];

  if (
    ticketId &&
    /investigate|root cause|cross.functional|recommend|best action/i.test(
      question,
    )
  ) {
    execute('get_complaint_detail', { complaint_id: ticketId }, toolCalls);
    execute('get_order_timeline', { complaint_id: ticketId }, toolCalls);
    execute(
      'get_inventory_availability',
      { complaint_id: ticketId },
      toolCalls,
    );
    execute('estimate_refund_impact', { complaint_id: ticketId }, toolCalls);
    const result = execute(
      'recommend_resolution',
      { complaint_id: ticketId },
      toolCalls,
    ) as ReturnType<typeof investigateComplaint>;
    return {
      answer: `${ticketId} is ${result.priority}. ${result.rationale}\n\nRecommended: ${result.recommendation.label}, estimated cost R$ ${result.recommendation.estimatedCost.toFixed(2)}, expected resolution ${result.recommendation.resolutionDays} day(s).\n\n${result.boundary}`,
      toolCalls,
    };
  }
  if (ticketId && /compare|option|scenario/i.test(question)) {
    const options = execute(
      'compare_resolution_options',
      { complaint_id: ticketId },
      toolCalls,
    ) as ReturnType<typeof compareResolutionOptions>;
    return {
      answer: options
        .map(
          (item) =>
            `${item.recommended ? 'Recommended · ' : ''}${item.label}: R$ ${item.estimatedCost.toFixed(2)}, ${item.resolutionDays} day(s), ${item.relationshipRecovery.toLowerCase()} recovery${item.feasible ? '' : ' (not currently feasible)'}`,
        )
        .join('\n'),
      toolCalls,
    };
  }
  if (ticketId && /draft|reply|response/i.test(question)) {
    const result = execute(
      'draft_customer_reply',
      { complaint_id: ticketId, tone: 'empathetic' },
      toolCalls,
    ) as { draft: string };
    return {
      answer: `Unsent customer reply draft:\n\n${result.draft}\n\nA human reviewer must verify the facts and resolution before use.`,
      toolCalls,
    };
  }
  if (ticketId) {
    const result = execute(
      'get_complaint_detail',
      { complaint_id: ticketId },
      toolCalls,
    ) as ReturnType<typeof compactComplaint>;
    return {
      answer: `${result.complaintId} is ${result.priorityLevel} priority (${result.priorityScore}). ${result.reasons.join('; ')}. Next action: ${result.nextAction}`,
      toolCalls,
    };
  }
  if (customerId) {
    const result = execute(
      'get_customer_360',
      { customer_id: customerId },
      toolCalls,
    ) as ReturnType<typeof rateCustomers>[number];
    return {
      answer: `${result.id} is value tier ${result.valueTier} (${result.valueScore}) with ${result.riskLevel.toLowerCase()} relationship risk (${result.riskScore}). ${result.scoreReasons.join('; ')}. Next action: ${result.nextAction}`,
      toolCalls,
    };
  }
  const top = prioritizeComplaints().slice(0, 3);
  const data = dashboard();
  execute('list_priority_complaints', {}, toolCalls);
  return {
    answer: `There are ${data.overdueComplaints} overdue complaints and ${data.unrespondedComplaints} without a first response. Start with ${top.map((item) => `${item.id} (${item.reviewScore ?? 'no'} star, ${item.lateDays} days late, score ${item.priorityScore})`).join(', ')}.`,
    toolCalls,
  };
}
