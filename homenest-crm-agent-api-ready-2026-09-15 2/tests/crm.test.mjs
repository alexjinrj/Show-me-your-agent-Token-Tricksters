import test from 'node:test';
import assert from 'node:assert/strict';
import {
  customerSources,
  complaintSources,
  dashboard,
  prioritizeComplaints,
  rateCustomers,
  relationshipRisk,
  updateFollowUp,
  valueScore,
} from '../lib/crm.ts';
import { crmTools, demoAgentAnswer, runCrmTool } from '../lib/agent.ts';
import {
  compareResolutionOptions,
  estimateFinancialImpact,
  getInventoryAvailability,
  getOrderTimeline,
  investigateComplaint,
} from '../lib/resolution.ts';

test('Olist snapshot keeps source counts and labelled CRM replay counts', () => {
  const data = dashboard();
  assert.equal(customerSources.length, 30);
  assert.equal(complaintSources.length, 24);
  assert.equal(data.sourceMeta.sourceRows.orders, 99441);
  assert.equal(data.overdueComplaints, 15);
  assert.equal(data.unrespondedComplaints, 4);
});

test('customer value and relationship risk use separate explainable inputs', () => {
  const selected = customerSources.find(
    (customer) => customer.id === 'CUS-001',
  );
  assert.equal(valueScore(selected), 86);
  assert.equal(relationshipRisk(2, 1, 1), 55);
  const rated = rateCustomers();
  assert.equal(
    rated.find((customer) => customer.id === 'CUS-001').valueTier,
    'A',
  );
  assert(
    rated.every((customer) => customer.scoreReasons[0].includes('Olist facts')),
  );
});

test('complaints are sorted by deterministic service priority', () => {
  const complaints = prioritizeComplaints();
  assert(
    complaints.every(
      (ticket, index) =>
        index === 0 ||
        complaints[index - 1].priorityScore >= ticket.priorityScore,
    ),
  );
  assert.equal(
    complaints.find((ticket) => ticket.id === 'TKT-004').priorityScore,
    100,
  );
  assert(
    complaints.every((ticket) =>
      ticket.reasons.some((reason) => reason.includes('Customer value')),
    ),
  );
  assert(
    complaints.every((ticket) =>
      ticket.reasons.some((reason) => reason.includes('Olist fact')),
    ),
  );
});

test('cross-functional investigation labels facts, replay fields and assumptions', () => {
  const timeline = getOrderTimeline('TKT-004');
  assert(timeline.some((event) => event.kind === 'Olist fact'));
  assert(timeline.some((event) => event.kind === 'CRM replay'));
  assert.equal(getInventoryAvailability('TKT-004').kind, 'Demo assumption');
  assert(
    estimateFinancialImpact('TKT-004').basis.every((line) => line.length > 0),
  );
  assert.match(investigateComplaint('TKT-004').boundary, /demo assumptions/i);
});

test('resolution comparison is deterministic and recommends one feasible option', () => {
  const options = compareResolutionOptions('TKT-004');
  assert.equal(options.length, 4);
  assert.equal(options.filter((option) => option.recommended).length, 1);
  assert(options.find((option) => option.recommended).feasible);
  assert.equal(options.find((option) => option.recommended).id, 'refund');
  assert.deepEqual(options, compareResolutionOptions('TKT-004'));
});

test('human approval enforces the state machine and records an audit trail', () => {
  const item = {
    id: 'APR-TKT-001',
    complaintId: 'TKT-001',
    customerId: 'CUS-001',
    title: 'Demo',
    owner: 'Customer Service',
    status: 'Pending Review',
    due: '2026-09-11T08:30:00+08:00',
    createdAt: '2026-09-11T12:00:00+08:00',
    replyDraft: 'Draft',
    internalDraft: 'Handoff',
    resolutionId: 'refund',
    resolutionLabel: 'Full refund',
    estimatedCost: 100,
    audit: [
      {
        at: '2026-09-11T12:00:00+08:00',
        actor: 'CRM Agent',
        action: 'Proposed',
        note: 'Demo',
      },
    ],
  };
  assert.throws(() => updateFollowUp(item, 'Completed'));
  const approved = updateFollowUp(
    item,
    'Approved',
    'Reviewed',
    '2026-09-11T12:05:00+08:00',
  );
  const started = updateFollowUp(
    approved,
    'In Progress',
    '',
    '2026-09-11T12:06:00+08:00',
  );
  const completed = updateFollowUp(
    started,
    'Completed',
    '',
    '2026-09-11T12:07:00+08:00',
  );
  assert.equal(completed.audit.length, 4);
});

test('CRM agent exposes strict investigation, decision, draft and proposal tools', () => {
  assert.equal(crmTools.length, 10);
  assert(crmTools.every((tool) => tool.strict === true));
  assert(
    crmTools.every((tool) => tool.parameters.additionalProperties === false),
  );
  const customer = runCrmTool('get_customer_360', { customer_id: 'CUS-004' });
  assert.equal(customer.id, 'CUS-004');
  assert.match(customer.boundary, /not a credit rating/i);
});

test('demo agent executes a multi-tool investigation and drafts safely', () => {
  const investigation = demoAgentAnswer(
    'Investigate TKT-004 and recommend the best action',
  );
  assert.equal(investigation.toolCalls.length, 5);
  assert.equal(investigation.toolCalls.at(-1).name, 'recommend_resolution');
  assert.match(investigation.answer, /Recommended: Full refund/);
  const draft = demoAgentAnswer('Draft a reply for TKT-014');
  assert.equal(draft.toolCalls[0].name, 'draft_customer_reply');
  assert.match(draft.answer, /Unsent customer reply draft/);
});
