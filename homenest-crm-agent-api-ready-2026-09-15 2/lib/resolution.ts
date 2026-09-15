import { prioritizeComplaints, type PrioritizedComplaint } from './crm.ts';

export type EvidenceKind = 'Olist fact' | 'CRM replay' | 'Demo assumption';
export type TimelineEvent = {
  label: string;
  at: string | null;
  kind: EvidenceKind;
  detail: string;
};
export type InventoryCheck = {
  replacementSku: string;
  availableUnits: number;
  reservedUnits: number;
  replenishmentDays: number;
  kind: 'Demo assumption';
};
export type FinancialImpact = {
  currency: 'BRL';
  orderValueProxy: number;
  fullRefundExposure: number;
  replacementCostEstimate: number;
  serviceCreditEstimate: number;
  basis: string[];
};
export type ResolutionOption = {
  id: 'refund' | 'reship' | 'credit' | 'monitor';
  label: string;
  estimatedCost: number;
  resolutionDays: number;
  relationshipRecovery: 'High' | 'Medium' | 'Low';
  feasible: boolean;
  conditions: string;
  risk: string;
  recommended: boolean;
};

const roundMoney = (value: number) => Math.round(value * 100) / 100;
export function complaintById(complaintId: string) {
  return prioritizeComplaints().find(
    (ticket) => ticket.id === complaintId.toUpperCase(),
  );
}
function requireComplaint(complaintId: string) {
  const ticket = complaintById(complaintId);
  if (!ticket)
    throw new Error(`Complaint ${complaintId.toUpperCase()} was not found.`);
  return ticket;
}

export function getOrderTimeline(complaintId: string): TimelineEvent[] {
  const ticket = requireComplaint(complaintId);
  return [
    {
      label: 'Order placed',
      at: ticket.sourcePurchaseAt,
      kind: 'Olist fact',
      detail: ticket.sourceOrderId,
    },
    {
      label: 'Promised delivery',
      at: ticket.sourceEstimatedDeliveryAt,
      kind: 'Olist fact',
      detail: 'Estimated delivery date in the Olist source record',
    },
    {
      label: 'Delivered',
      at: ticket.sourceDeliveredAt,
      kind: 'Olist fact',
      detail:
        ticket.lateDays > 0
          ? `${ticket.lateDays} days after the estimate`
          : 'No recorded delay',
    },
    {
      label: 'Complaint opened',
      at: ticket.openedAt,
      kind: 'CRM replay',
      detail: ticket.issue,
    },
    {
      label: 'SLA deadline',
      at: ticket.dueAt,
      kind: 'CRM replay',
      detail:
        ticket.overdueHours > 0
          ? `${ticket.overdueHours.toFixed(1)} hours overdue`
          : 'Within SLA',
    },
  ];
}

export function getInventoryAvailability(complaintId: string): InventoryCheck {
  const ticket = requireComplaint(complaintId);
  const numericId = Number(ticket.id.slice(-3));
  return {
    replacementSku: `REPL-${ticket.sourceOrderId.slice(0, 6).toUpperCase()}`,
    availableUnits: (numericId * 7) % 5,
    reservedUnits: numericId % 3,
    replenishmentDays: 4 + (numericId % 5),
    kind: 'Demo assumption',
  };
}

export function estimateFinancialImpact(complaintId: string): FinancialImpact {
  const ticket = requireComplaint(complaintId);
  const orderValueProxy = roundMoney(
    ticket.customer.spend / Math.max(ticket.customer.orderCount, 1),
  );
  return {
    currency: 'BRL',
    orderValueProxy,
    fullRefundExposure: orderValueProxy,
    replacementCostEstimate: roundMoney(orderValueProxy * 0.42 + 35),
    serviceCreditEstimate: roundMoney(Math.min(orderValueProxy * 0.1, 150)),
    basis: [
      'Order value is proxied from customer payment total divided by order count.',
      'Replacement cost assumes 42% product cost plus R$35 handling and delivery.',
      'Service credit is 10% of proxy order value, capped at R$150.',
      'All cost estimates are demo assumptions, not Olist accounting facts.',
    ],
  };
}

function recommendedId(
  ticket: PrioritizedComplaint,
  inventory: InventoryCheck,
) {
  if (ticket.reviewScore === 1 && ticket.lateDays >= 30)
    return 'refund' as const;
  if (inventory.availableUnits > 0) return 'reship' as const;
  return 'refund' as const;
}

export function compareResolutionOptions(
  complaintId: string,
): ResolutionOption[] {
  const ticket = requireComplaint(complaintId);
  const inventory = getInventoryAvailability(complaintId);
  const financial = estimateFinancialImpact(complaintId);
  const recommended = recommendedId(ticket, inventory);
  return [
    {
      id: 'refund',
      label: 'Full refund',
      estimatedCost: financial.fullRefundExposure,
      resolutionDays: 2,
      relationshipRecovery: 'High',
      feasible: true,
      conditions: 'Requires finance approval and verified refund eligibility.',
      risk: 'Highest direct cost; does not replace the product.',
      recommended: recommended === 'refund',
    },
    {
      id: 'reship',
      label: 'Priority replacement',
      estimatedCost: financial.replacementCostEstimate,
      resolutionDays:
        inventory.availableUnits > 0 ? 3 : inventory.replenishmentDays + 3,
      relationshipRecovery: 'High',
      feasible: inventory.availableUnits > 0,
      conditions:
        inventory.availableUnits > 0
          ? `${inventory.availableUnits} assumed replacement unit(s) available.`
          : `Wait ${inventory.replenishmentDays} assumed replenishment days.`,
      risk: 'Another fulfilment failure would further damage the relationship.',
      recommended: recommended === 'reship',
    },
    {
      id: 'credit',
      label: 'Service credit',
      estimatedCost: financial.serviceCreditEstimate,
      resolutionDays: 1,
      relationshipRecovery: ticket.lateDays >= 30 ? 'Low' : 'Medium',
      feasible: true,
      conditions:
        'Requires customer acceptance and a valid future purchase channel.',
      risk: 'May be inadequate for a severe delay or one-star review.',
      recommended: false,
    },
    {
      id: 'monitor',
      label: 'Explain and monitor',
      estimatedCost: 0,
      resolutionDays: 7,
      relationshipRecovery: 'Low',
      feasible: true,
      conditions: 'Provide a fact-based update and monitor the case.',
      risk: 'Low financial cost but high relationship risk for severe complaints.',
      recommended: false,
    },
  ];
}

export function investigateComplaint(complaintId: string) {
  const ticket = requireComplaint(complaintId);
  const timeline = getOrderTimeline(complaintId);
  const inventory = getInventoryAvailability(complaintId);
  const financial = estimateFinancialImpact(complaintId);
  const options = compareResolutionOptions(complaintId);
  const recommendation = options.find((option) => option.recommended)!;
  return {
    complaintId: ticket.id,
    customerId: ticket.customerId,
    priority: `${ticket.priorityLevel}/${ticket.priorityScore}`,
    timeline,
    inventory,
    financial,
    options,
    recommendation,
    rationale:
      recommendation.id === 'refund'
        ? 'A one-star review with an extreme delivery delay makes a fast refund the strongest recovery option under the demo policy.'
        : 'A replacement is available and can resolve the fulfilment failure at lower estimated cost than a full refund.',
    boundary:
      'Order, review and delivery dates are Olist facts. Ticket SLA is CRM replay. Inventory and financial impacts are labelled demo assumptions.',
  };
}
