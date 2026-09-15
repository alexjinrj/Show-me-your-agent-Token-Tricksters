import olistSnapshot from '../data/olist-snapshot.json' with { type: 'json' };

export type TicketStatus =
  | 'READY'
  | 'WAITING_WAREHOUSE'
  | 'WAITING_FINANCE'
  | 'WAITING_CUSTOMER';
export type ValueTier = 'A' | 'B' | 'C' | 'Prospect';
export type RiskLevel = 'High' | 'Medium' | 'Low';
export type ApprovalStatus =
  | 'Pending Review'
  | 'Approved'
  | 'Rejected'
  | 'In Progress'
  | 'Completed';

export type CustomerSource = {
  id: string;
  name: string;
  type: 'Anonymous';
  orderCount: number;
  spend: number;
  onboarding: 'Not provided';
  paymentTerms: string;
  sourceCustomerId: string;
  city: string;
  state: string;
  lastOrderAt: string;
  averageReviewScore: number | null;
  lateDeliveryCount: number;
};

export type ComplaintSource = {
  id: string;
  customerId: string;
  orderId: string;
  sourceOrderId: string;
  status: TicketStatus;
  issue: string;
  openedAt: string;
  dueAt: string;
  firstResponseAt: string | null;
  reviewScore: number | null;
  reviewText: string | null;
  lateDays: number;
  sourcePurchaseAt: string;
  sourceDeliveredAt: string | null;
  sourceEstimatedDeliveryAt: string | null;
};

export type RatedCustomer = CustomerSource & {
  valueScore: number;
  valueTier: ValueTier;
  riskScore: number;
  riskLevel: RiskLevel;
  openComplaints: number;
  overdueComplaints: number;
  unrespondedComplaints: number;
  scoreReasons: string[];
  nextAction: string;
};

export type PrioritizedComplaint = ComplaintSource & {
  customer: RatedCustomer;
  priorityScore: number;
  priorityLevel: 'Critical' | 'High' | 'Standard';
  overdueHours: number;
  ageHours: number;
  reasons: string[];
  ownerRole: string;
  nextAction: string;
  replyDraft: string;
  internalDraft: string;
};

export type AuditEntry = {
  at: string;
  actor: 'CRM Agent' | 'Human reviewer';
  action: string;
  note: string;
};

export type FollowUp = {
  id: string;
  complaintId: string;
  customerId: string;
  title: string;
  owner: string;
  status: ApprovalStatus;
  due: string;
  createdAt: string;
  replyDraft: string;
  internalDraft: string;
  resolutionId: string;
  resolutionLabel: string;
  estimatedCost: number;
  audit: AuditEntry[];
};

export const statusLabel: Record<TicketStatus, string> = {
  READY: 'Ready for service',
  WAITING_WAREHOUSE: 'Waiting for fulfilment check',
  WAITING_FINANCE: 'Waiting for finance check',
  WAITING_CUSTOMER: 'Waiting for customer information',
};

export function updateFollowUp(
  item: FollowUp,
  next: ApprovalStatus,
  note = '',
  at = new Date().toISOString(),
) {
  const allowed =
    (item.status === 'Pending Review' &&
      (next === 'Approved' || next === 'Rejected')) ||
    (item.status === 'Approved' && next === 'In Progress') ||
    (item.status === 'In Progress' && next === 'Completed');
  if (!allowed)
    throw new Error(`Invalid transition: ${item.status} → ${next}.`);
  return {
    ...item,
    status: next,
    audit: [
      ...item.audit,
      {
        at,
        actor: 'Human reviewer' as const,
        action: next,
        note: note || `Marked ${next}`,
      },
    ],
  };
}

export const sourceMeta = olistSnapshot.meta;
export const snapshotTime = sourceMeta.replayAsOf;
export const customerSources: CustomerSource[] = olistSnapshot.customers.map(
  (customer) => ({
    ...customer,
    name: `Olist Anonymous Customer ${customer.id.slice(-3)}`,
    type: 'Anonymous',
    onboarding: 'Not provided',
    paymentTerms:
      customer.paymentTerms === '数据未提供'
        ? 'Not provided'
        : customer.paymentTerms,
  }),
);
export const complaintSources: ComplaintSource[] = olistSnapshot.complaints.map(
  (complaint) => ({
    ...complaint,
    issue:
      complaint.reviewScore !== null && complaint.lateDays > 0
        ? `${complaint.reviewScore}/5 review; delivered ${complaint.lateDays} days late`
        : complaint.reviewScore !== null
          ? `${complaint.reviewScore}/5 customer review`
          : `Delivery exception; ${complaint.lateDays} days late`,
    status: complaint.status as TicketStatus,
  }),
);

const hoursBetween = (later: string, earlier: string) =>
  Math.max(0, (new Date(later).getTime() - new Date(earlier).getTime()) / 36e5);
const percentile = (value: number, values: number[]) =>
  values.length
    ? values.filter((candidate) => candidate <= value).length / values.length
    : 0;

/** Cohort-relative value score: payment total 50%, frequency 30%, recency 20%. */
export function valueScore(customer: CustomerSource) {
  if (!customer.orderCount) return 0;
  const spend = percentile(
    customer.spend,
    customerSources.map((item) => item.spend),
  );
  const frequency = percentile(
    customer.orderCount,
    customerSources.map((item) => item.orderCount),
  );
  const recency = percentile(
    Date.parse(customer.lastOrderAt),
    customerSources.map((item) => Date.parse(item.lastOrderAt)),
  );
  return Math.min(100, Math.round(spend * 50 + frequency * 30 + recency * 20));
}

export function customerValueTier(
  score: number,
  orderCount: number,
): ValueTier {
  if (!orderCount) return 'Prospect';
  if (score >= 75) return 'A';
  if (score >= 50) return 'B';
  return 'C';
}

export function relationshipRisk(
  open: number,
  overdue: number,
  unresponded: number,
  reviewPenalty = 0,
  lateDeliveries = 0,
) {
  return Math.min(
    100,
    open * 10 +
      overdue * 15 +
      unresponded * 20 +
      reviewPenalty +
      Math.min(20, lateDeliveries * 10),
  );
}

export function rateCustomers() {
  return customerSources.map((customer): RatedCustomer => {
    const own = complaintSources.filter(
      (ticket) => ticket.customerId === customer.id,
    );
    const overdue = own.filter(
      (ticket) => new Date(ticket.dueAt) < new Date(snapshotTime),
    ).length;
    const unresponded = own.filter((ticket) => !ticket.firstResponseAt).length;
    const lowReviews = own.filter(
      (ticket) => ticket.reviewScore !== null && ticket.reviewScore <= 2,
    );
    const reviewPenalty = lowReviews.reduce(
      (total, ticket) => total + (ticket.reviewScore === 1 ? 20 : 10),
      0,
    );
    const value = valueScore(customer);
    const risk = relationshipRisk(
      own.length,
      overdue,
      unresponded,
      reviewPenalty,
      customer.lateDeliveryCount,
    );
    return {
      ...customer,
      valueScore: value,
      valueTier: customerValueTier(value, customer.orderCount),
      riskScore: risk,
      riskLevel: risk >= 65 ? 'High' : risk >= 35 ? 'Medium' : 'Low',
      openComplaints: own.length,
      overdueComplaints: overdue,
      unrespondedComplaints: unresponded,
      scoreReasons: [
        `Olist facts: R$ ${customer.spend.toFixed(2)} paid, ${customer.orderCount} order(s), last order ${customer.lastOrderAt.slice(0, 10)}`,
        `Experience signals: ${lowReviews.length} low review(s), ${customer.lateDeliveryCount} late delivery event(s); CRM replay: ${own.length} open, ${overdue} overdue, ${unresponded} unresponded`,
      ],
      nextAction: unresponded
        ? 'Verify that no reply is missing, then acknowledge the complaint immediately.'
        : overdue
          ? 'Ask fulfilment to verify the order timeline and provide a fact-based update.'
          : lowReviews.length
            ? 'Review the original feedback and prepare an evidence-based recovery plan.'
            : 'No urgent relationship action; continue normal engagement.',
    };
  });
}

const ownerAndAction: Record<TicketStatus, [string, string]> = {
  READY: [
    'Customer Service',
    'Verify the review and order timeline before responding.',
  ],
  WAITING_WAREHOUSE: [
    'CRM + Fulfilment',
    'Verify promised and actual delivery dates and the delay cause.',
  ],
  WAITING_FINANCE: [
    'CRM + Finance',
    'Verify refund eligibility and status before making a commitment.',
  ],
  WAITING_CUSTOMER: [
    'Customer Service',
    'Send one clear request for the missing customer information.',
  ],
};

export function prioritizeComplaints() {
  const customers = new Map(
    rateCustomers().map((customer) => [customer.id, customer]),
  );
  return complaintSources
    .map((ticket): PrioritizedComplaint => {
      const customer = customers.get(ticket.customerId)!;
      const overdueHours = hoursBetween(snapshotTime, ticket.dueAt);
      const ageHours = hoursBetween(snapshotTime, ticket.openedAt);
      const slaPoints = Math.min(40, (overdueHours / 48) * 40);
      const reviewPoints =
        ticket.reviewScore === 1 ? 20 : ticket.reviewScore === 2 ? 12 : 0;
      const latePoints = Math.min(10, ticket.lateDays / 2);
      const priority = Math.min(
        100,
        Math.round(
          slaPoints +
            (!ticket.firstResponseAt ? 25 : 0) +
            reviewPoints +
            latePoints +
            customer.riskScore * 0.05 +
            customer.valueScore * 0.02,
        ),
      );
      const [ownerRole, baseAction] = ownerAndAction[ticket.status];
      const reasons = [
        `Olist fact: ${ticket.reviewScore ?? 'no'}-star review${ticket.lateDays > 0 ? ` and ${ticket.lateDays} days late` : ''}`,
        overdueHours
          ? `CRM replay: SLA overdue by ${overdueHours.toFixed(1)} hours`
          : `CRM replay: ${hoursBetween(ticket.dueAt, snapshotTime).toFixed(1)} hours before SLA`,
        ticket.firstResponseAt
          ? 'CRM replay: first response recorded'
          : 'CRM replay: no first response recorded',
        `Customer value ${customer.valueTier}/${customer.valueScore} contributes only 2% of priority`,
      ];
      const nextAction = !ticket.firstResponseAt
        ? `Confirm there is no unsynchronised reply, acknowledge the customer, then ${baseAction.toLowerCase()}`
        : baseAction;
      return {
        ...ticket,
        customer,
        overdueHours,
        ageHours,
        priorityScore: priority,
        priorityLevel:
          priority >= 70 ? 'Critical' : priority >= 50 ? 'High' : 'Standard',
        reasons,
        ownerRole,
        nextAction,
        replyDraft: `Hello, we have received your feedback about order ${ticket.orderId}. We are verifying the order and delivery timeline and will update you after review. This draft has not been sent.`,
        internalDraft: `${ownerRole}: verify ${ticket.id} / ${ticket.orderId}, record the evidence and response time, then return the case to CRM.`,
      };
    })
    .sort(
      (a, b) => b.priorityScore - a.priorityScore || a.id.localeCompare(b.id),
    );
}

export function dashboard() {
  const customers = rateCustomers();
  const complaints = prioritizeComplaints();
  return {
    sourceMeta,
    customers,
    complaints,
    highRiskCustomers: customers.filter(
      (customer) => customer.riskLevel === 'High',
    ).length,
    overdueComplaints: complaints.filter((ticket) => ticket.overdueHours > 0)
      .length,
    unrespondedComplaints: complaints.filter(
      (ticket) => !ticket.firstResponseAt,
    ).length,
    aTierCustomers: customers.filter((customer) => customer.valueTier === 'A')
      .length,
    lowReviewComplaints: complaints.filter(
      (ticket) => ticket.reviewScore !== null && ticket.reviewScore <= 2,
    ).length,
    lateDeliveryComplaints: complaints.filter((ticket) => ticket.lateDays > 0)
      .length,
  };
}
