'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  BadgeAlert,
  Bot,
  Building2,
  Check,
  ChevronRight,
  CircleDollarSign,
  ClipboardCheck,
  Database,
  Download,
  Filter,
  GitCompareArrows,
  LayoutDashboard,
  MessageSquareText,
  PackageCheck,
  Search,
  ShieldCheck,
  Sparkles,
  UserRoundSearch,
  Users,
} from 'lucide-react';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { CrmAgentPanel } from '@/components/crm-agent';
import {
  dashboard,
  snapshotTime,
  statusLabel,
  updateFollowUp,
  type ApprovalStatus,
  type FollowUp,
  type PrioritizedComplaint,
  type RatedCustomer,
  type RiskLevel,
  type ValueTier,
} from '@/lib/crm';
import {
  compareResolutionOptions,
  investigateComplaint,
  type ResolutionOption,
} from '@/lib/resolution';

const navigation = [
  { id: 'today', name: 'Today', icon: LayoutDashboard },
  { id: 'customers', name: 'Customers', icon: Users },
  { id: 'complaints', name: 'Complaint Queue', icon: MessageSquareText },
  { id: 'resolution', name: 'Resolution Lab', icon: GitCompareArrows },
  { id: 'approvals', name: 'Approvals', icon: ClipboardCheck },
] as const;
type PageId = (typeof navigation)[number]['id'];

const STORE = 'homenest.crm.approvals.en.v1';
const pageCopy: Record<PageId, { title: string; description: string }> = {
  today: {
    title: 'Customer Relationship Command Center',
    description: 'Prioritise the customers who need a verified response today.',
  },
  customers: {
    title: 'Customer Intelligence',
    description:
      'Value and relationship risk are scored separately, with evidence for every result.',
  },
  complaints: {
    title: 'Complaint Triage',
    description:
      'Rank open cases using SLA, response status, customer experience and relationship risk.',
  },
  resolution: {
    title: 'Cross-functional Resolution Lab',
    description:
      'Trace the order, check assumed replacement inventory, estimate financial impact and compare options.',
  },
  approvals: {
    title: 'Human Approval Queue',
    description:
      'Review proposed resolutions before any operational or customer-facing action.',
  },
};

const money = (value: number) =>
  new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(
    value,
  );
const formatStamp = (value: string) => {
  const singapore = new Date(new Date(value).getTime() + 8 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 16)
    .replace('T', ' ');
  return `${singapore} SGT`;
};
const riskClass = (value: RiskLevel) =>
  value === 'High'
    ? 'risk-high'
    : value === 'Medium'
      ? 'risk-medium'
      : 'risk-low';
const tierClass = (value: ValueTier) =>
  value === 'A'
    ? 'tier-a'
    : value === 'B'
      ? 'tier-b'
      : value === 'Prospect'
        ? 'tier-new'
        : 'tier-c';

function SideNavigation({
  page,
  onChange,
}: {
  page: PageId;
  onChange: (page: PageId) => void;
}) {
  const { isMobile, setOpenMobile } = useSidebar();
  return (
    <Sidebar>
      <SidebarHeader className="brand">
        <div className="brand-mark">
          <Building2 size={24} />
        </div>
        <div>
          <strong>HomeNest CRM</strong>
          <small>Service Recovery Agent</small>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <p className="nav-label">CUSTOMER OPERATIONS</p>
          <SidebarMenu>
            {navigation.map((item) => (
              <SidebarMenuItem key={item.id}>
                <SidebarMenuButton
                  size="lg"
                  isActive={page === item.id}
                  aria-current={page === item.id ? 'page' : undefined}
                  onClick={() => {
                    onChange(item.id);
                    if (isMobile) setOpenMobile(false);
                  }}
                >
                  <item.icon />
                  <span>{item.name}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
        <div className="sidebar-note">
          <ShieldCheck size={18} />
          <div>
            <b>Explainable by design</b>
            <p>Scores, evidence, assumptions and approvals remain separate.</p>
          </div>
        </div>
      </SidebarContent>
      <SidebarFooter className="sidebar-footer">
        <Database size={17} />
        <div>
          <b>Olist public dataset</b>
          <small>2016–2018 · Brazil e-commerce</small>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}

function Metric({
  label,
  value,
  detail,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  detail: string;
  tone?: string;
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="empty-state">
      <UserRoundSearch size={26} />
      <p>{text}</p>
    </div>
  );
}

export default function Home() {
  const data = useMemo(() => dashboard(), []);
  const [page, setPage] = useState<PageId>('today');
  const [search, setSearch] = useState('');
  const [tier, setTier] = useState<'All' | ValueTier>('All');
  const [risk, setRisk] = useState<'All' | RiskLevel>('All');
  const [priority, setPriority] = useState<
    'All' | 'Critical' | 'High' | 'Standard'
  >('All');
  const [selectedCustomer, setSelectedCustomer] =
    useState<RatedCustomer | null>(null);
  const [selectedComplaint, setSelectedComplaint] =
    useState<PrioritizedComplaint | null>(null);
  const [resolutionTicketId, setResolutionTicketId] = useState(
    data.complaints[0].id,
  );
  const [selectedResolutionId, setSelectedResolutionId] = useState<string>('');
  const [replyDraft, setReplyDraft] = useState('');
  const [internalDraft, setInternalDraft] = useState('');
  const [approvalNote, setApprovalNote] = useState('');
  const [followups, setFollowups] = useState<FollowUp[]>([]);
  const [storageReady, setStorageReady] = useState(false);
  const [notice, setNotice] = useState('');

  const investigation = useMemo(
    () => investigateComplaint(resolutionTicketId),
    [resolutionTicketId],
  );
  const options = useMemo(
    () => compareResolutionOptions(resolutionTicketId),
    [resolutionTicketId],
  );
  const selectedResolution =
    options.find((item) => item.id === selectedResolutionId) ||
    options.find((item) => item.recommended)!;

  useEffect(() => {
    const id = window.setTimeout(() => {
      try {
        const raw = localStorage.getItem(STORE);
        if (raw) {
          const saved: unknown = JSON.parse(raw);
          if (Array.isArray(saved)) setFollowups(saved as FollowUp[]);
        }
      } catch {
        setNotice(
          'Saved approvals could not be read. Existing browser data was not overwritten.',
        );
      } finally {
        setStorageReady(true);
      }
    }, 0);
    return () => window.clearTimeout(id);
  }, []);

  const persist = (next: FollowUp[]) => {
    if (!storageReady) return;
    try {
      localStorage.setItem(STORE, JSON.stringify(next));
      setFollowups(next);
      setNotice('The approval record was saved on this device.');
    } catch {
      setNotice('The browser could not save this record.');
    }
  };

  const openComplaint = (ticket: PrioritizedComplaint) => {
    setSelectedComplaint(ticket);
    setReplyDraft(ticket.replyDraft);
    setInternalDraft(ticket.internalDraft);
  };

  const openResolutionLab = (ticket: PrioritizedComplaint) => {
    setResolutionTicketId(ticket.id);
    setSelectedResolutionId('');
    setSelectedComplaint(null);
    setPage('resolution');
  };

  const submitForApproval = (
    ticket: PrioritizedComplaint,
    resolution: ResolutionOption,
  ) => {
    const existing = followups.find(
      (item) => item.complaintId === ticket.id && item.status !== 'Rejected',
    );
    if (existing) {
      setNotice(`${ticket.id} already has an active approval record.`);
      setPage('approvals');
      return;
    }
    const createdAt = new Date().toISOString();
    const next: FollowUp = {
      id: `APR-${ticket.id}`,
      complaintId: ticket.id,
      customerId: ticket.customerId,
      title: ticket.issue,
      owner: ticket.ownerRole,
      status: 'Pending Review',
      due: ticket.dueAt,
      createdAt,
      replyDraft: replyDraft || ticket.replyDraft,
      internalDraft: internalDraft || ticket.internalDraft,
      resolutionId: resolution.id,
      resolutionLabel: resolution.label,
      estimatedCost: resolution.estimatedCost,
      audit: [
        {
          at: createdAt,
          actor: 'CRM Agent',
          action: 'Proposed',
          note: `${resolution.label} submitted for human review`,
        },
      ],
    };
    persist([next, ...followups]);
    setPage('approvals');
  };

  const transition = (item: FollowUp, status: ApprovalStatus) => {
    try {
      const next = updateFollowUp(item, status, approvalNote);
      persist(
        followups.map((candidate) =>
          candidate.id === item.id ? next : candidate,
        ),
      );
      setApprovalNote('');
    } catch (error) {
      setNotice((error as Error).message);
    }
  };

  const filteredCustomers = data.customers.filter(
    (customer) =>
      `${customer.id} ${customer.name}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (tier === 'All' || customer.valueTier === tier) &&
      (risk === 'All' || customer.riskLevel === risk),
  );
  const filteredComplaints = data.complaints.filter(
    (ticket) =>
      `${ticket.id} ${ticket.customer.name} ${ticket.orderId} ${ticket.issue}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (priority === 'All' || ticket.priorityLevel === priority),
  );
  const copy = pageCopy[page];
  const resolutionTicket = data.complaints.find(
    (ticket) => ticket.id === resolutionTicketId,
  )!;

  return (
    <SidebarProvider>
      <SideNavigation
        page={page}
        onChange={(next) => {
          setPage(next);
          setSearch('');
          setNotice('');
        }}
      />
      <SidebarInset>
        <header className="topbar">
          <div className="topbar-left">
            <SidebarTrigger aria-label="Toggle navigation" />
            <span>HomeNest</span>
            <ChevronRight size={14} />
            <b>{navigation.find((item) => item.id === page)?.name}</b>
          </div>
          <span className="snapshot-pill">
            <span /> Olist facts · CRM replay {formatStamp(snapshotTime)}
          </span>
        </header>
        <main className="workspace">
          <div className="page-heading">
            <div>
              <p className="eyebrow">CUSTOMER RELATIONSHIP</p>
              <h1>{copy.title}</h1>
              <p>{copy.description}</p>
            </div>
            <Button
              variant="outline"
              onClick={() => {
                const blob = new Blob([JSON.stringify(data, null, 2)], {
                  type: 'application/json',
                });
                const url = URL.createObjectURL(blob);
                const anchor = document.createElement('a');
                anchor.href = url;
                anchor.download = 'homenest-crm-analysis.json';
                anchor.click();
                URL.revokeObjectURL(url);
              }}
            >
              <Download size={16} />
              Export analysis
            </Button>
          </div>
          {notice && (
            <output className="notice">
              <Check size={16} />
              {notice}
            </output>
          )}

          {page === 'today' && (
            <>
              <section className="metrics-grid">
                <Metric
                  label="High relationship risk"
                  value={`${data.highRiskCustomers}`}
                  detail="Explainable relationship signals"
                  tone="danger"
                />
                <Metric
                  label="Overdue complaints"
                  value={`${data.overdueComplaints}`}
                  detail={`${data.complaints.length} open replay tickets`}
                  tone="warning"
                />
                <Metric
                  label="No first response"
                  value={`${data.unrespondedComplaints}`}
                  detail="Verify before contacting"
                  tone="focus"
                />
                <Metric
                  label="Pending approvals"
                  value={`${followups.filter((item) => item.status === 'Pending Review').length}`}
                  detail="Human decision required"
                />
              </section>
              <section className="agent-brief">
                <div className="agent-icon">
                  <Sparkles size={22} />
                </div>
                <div>
                  <p className="eyebrow">
                    AGENT BRIEF · CROSS-FUNCTIONAL INVESTIGATION
                  </p>
                  <h2>
                    Complaint evidence becomes a reviewable recovery decision
                  </h2>
                  <p>
                    The agent reads customer, order and delivery facts, checks
                    labelled inventory and finance assumptions, compares
                    resolution options, and stops for human approval.
                  </p>
                </div>
                <Button onClick={() => setPage('resolution')}>
                  Open Resolution Lab
                  <ChevronRight size={16} />
                </Button>
              </section>
              <div className="dashboard-grid">
                <section className="panel">
                  <div className="panel-head">
                    <div>
                      <p className="eyebrow">NEXT BEST ACTION</p>
                      <h2>Priority service queue</h2>
                    </div>
                    <button onClick={() => setPage('complaints')}>
                      View all
                    </button>
                  </div>
                  <div className="queue-list">
                    {data.complaints.slice(0, 5).map((ticket) => (
                      <button
                        key={ticket.id}
                        className="queue-row"
                        onClick={() => openComplaint(ticket)}
                      >
                        <span
                          className={`priority-badge p-${ticket.priorityLevel}`}
                        >
                          {ticket.priorityScore}
                        </span>
                        <span className="queue-main">
                          <b>
                            {ticket.id} · {ticket.customer.name}
                          </b>
                          <small>{ticket.issue}</small>
                        </span>
                        <span className="queue-meta">
                          <b>{ticket.priorityLevel}</b>
                          <small>
                            {ticket.overdueHours
                              ? `${ticket.overdueHours.toFixed(1)}h overdue`
                              : 'Within SLA'}
                          </small>
                        </span>
                        <ChevronRight size={16} />
                      </button>
                    ))}
                  </div>
                </section>
                <section className="panel matrix-card">
                  <div className="panel-head">
                    <div>
                      <p className="eyebrow">RELATIONSHIP MAP</p>
                      <h2>Customer value × relationship risk</h2>
                    </div>
                    <span>Select a customer</span>
                  </div>
                  <div
                    className="matrix"
                    aria-label="Customer value and relationship risk matrix"
                  >
                    <span className="axis y">Higher relationship risk</span>
                    <span className="axis x">Higher customer value</span>
                    <div className="quadrant q1">Retain</div>
                    <div className="quadrant q2">Recover</div>
                    <div className="quadrant q3">Serve</div>
                    <div className="quadrant q4">Develop</div>
                    {data.customers
                      .filter((customer) => customer.orderCount)
                      .map((customer) => (
                        <button
                          key={customer.id}
                          className={`matrix-point ${riskClass(customer.riskLevel)}`}
                          style={{
                            left: `${Math.max(6, customer.valueScore)}%`,
                            bottom: `${Math.max(6, customer.riskScore)}%`,
                          }}
                          title={`${customer.id}: value ${customer.valueScore}, risk ${customer.riskScore}`}
                          aria-label={`View ${customer.name}`}
                          onClick={() => setSelectedCustomer(customer)}
                        >
                          {customer.id.slice(-2)}
                        </button>
                      ))}
                  </div>
                </section>
              </div>
              <section className="score-note">
                <ShieldCheck size={20} />
                <div>
                  <b>Evidence boundary</b>
                  <p>
                    Orders, payments, anonymous customer IDs, reviews and
                    delivery dates come from Olist. Ticket workflow, SLA and
                    response times are CRM replay fields. Replacement inventory
                    and financial impacts are explicit demo assumptions.
                  </p>
                </div>
              </section>
            </>
          )}

          {page === 'customers' && (
            <>
              <section className="filterbar">
                <div className="searchbox">
                  <Search size={16} />
                  <Input
                    aria-label="Search customers"
                    placeholder="Search name or customer ID"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                  />
                </div>
                <div className="filter-controls">
                  <Filter size={16} />
                  <Select
                    value={tier}
                    onValueChange={(value) =>
                      value && setTier(value as typeof tier)
                    }
                    items={['All', 'A', 'B', 'C', 'Prospect'].map((value) => ({
                      value,
                      label: value,
                    }))}
                  >
                    <SelectTrigger aria-label="Value tier">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {['All', 'A', 'B', 'C', 'Prospect'].map((item) => (
                        <SelectItem key={item} value={item}>
                          {item === 'All' ? 'All value tiers' : `Tier ${item}`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={risk}
                    onValueChange={(value) =>
                      value && setRisk(value as typeof risk)
                    }
                    items={['All', 'High', 'Medium', 'Low'].map((value) => ({
                      value,
                      label: value,
                    }))}
                  >
                    <SelectTrigger aria-label="Relationship risk">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {['All', 'High', 'Medium', 'Low'].map((item) => (
                        <SelectItem key={item} value={item}>
                          {item === 'All' ? 'All risk levels' : `${item} risk`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </section>
              <section className="panel table-panel">
                <div className="panel-head">
                  <div>
                    <p className="eyebrow">CUSTOMER 360 · OLIST</p>
                    <h2>Customer portfolio</h2>
                  </div>
                  <span>{filteredCustomers.length} anonymous customers</span>
                </div>
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Customer</TableHead>
                        <TableHead>Value</TableHead>
                        <TableHead>Relationship risk</TableHead>
                        <TableHead>Orders / payment</TableHead>
                        <TableHead>Review / delay</TableHead>
                        <TableHead>Next action</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredCustomers.map((customer) => (
                        <TableRow
                          key={customer.id}
                          className="clickable"
                          onClick={() => setSelectedCustomer(customer)}
                        >
                          <TableCell>
                            <b>{customer.name}</b>
                            <small>
                              {customer.id} · {customer.city}, {customer.state}
                            </small>
                          </TableCell>
                          <TableCell>
                            <span
                              className={`tier ${tierClass(customer.valueTier)}`}
                            >
                              {customer.valueTier}
                            </span>
                            <small>{customer.valueScore} points</small>
                          </TableCell>
                          <TableCell>
                            <span
                              className={`risk-label ${riskClass(customer.riskLevel)}`}
                            >
                              {customer.riskLevel}
                            </span>
                            <small>{customer.riskScore} points</small>
                          </TableCell>
                          <TableCell>
                            <b>{customer.orderCount} order(s)</b>
                            <small>{money(customer.spend)}</small>
                          </TableCell>
                          <TableCell>
                            <b>
                              {customer.averageReviewScore?.toFixed(1) ?? '—'}{' '}
                              stars / {customer.lateDeliveryCount} late
                            </b>
                            <small>
                              {customer.openComplaints} derived complaint(s)
                            </small>
                          </TableCell>
                          <TableCell>
                            <span className="next-action">
                              {customer.nextAction}
                            </span>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {!filteredCustomers.length && (
                  <EmptyState text="No customers match the filters." />
                )}
              </section>
            </>
          )}

          {page === 'complaints' && (
            <>
              <section className="filterbar">
                <div className="searchbox">
                  <Search size={16} />
                  <Input
                    aria-label="Search complaints"
                    placeholder="Search complaint, customer or order"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                  />
                </div>
                <Select
                  value={priority}
                  onValueChange={(value) =>
                    value && setPriority(value as typeof priority)
                  }
                  items={['All', 'Critical', 'High', 'Standard'].map(
                    (value) => ({ value, label: value }),
                  )}
                >
                  <SelectTrigger aria-label="Priority">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {['All', 'Critical', 'High', 'Standard'].map((item) => (
                      <SelectItem key={item} value={item}>
                        {item === 'All' ? 'All priorities' : item}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </section>
              <section className="score-formula">
                <div>
                  <BadgeAlert size={20} />
                  <b>Complaint priority</b>
                </div>
                <p>
                  SLA severity (40) + no first response (25) + low review (20) +
                  delivery delay (10) + relationship risk (5%) + customer value
                  (2%).
                </p>
              </section>
              <section className="panel table-panel">
                <div className="panel-head">
                  <div>
                    <p className="eyebrow">SERVICE QUEUE</p>
                    <h2>Complaint handling order</h2>
                  </div>
                  <span>{filteredComplaints.length} open tickets</span>
                </div>
                <div className="table-scroll">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Priority</TableHead>
                        <TableHead>Complaint and customer</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>SLA</TableHead>
                        <TableHead>Value / risk</TableHead>
                        <TableHead>Owner</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredComplaints.map((ticket) => (
                        <TableRow
                          key={ticket.id}
                          className="clickable"
                          onClick={() => openComplaint(ticket)}
                        >
                          <TableCell>
                            <span
                              className={`priority-badge p-${ticket.priorityLevel}`}
                            >
                              {ticket.priorityScore}
                            </span>
                            <small>{ticket.priorityLevel}</small>
                          </TableCell>
                          <TableCell>
                            <b>
                              {ticket.id} · {ticket.customer.name}
                            </b>
                            <small>
                              {ticket.orderId} · {ticket.issue}
                            </small>
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline">
                              {statusLabel[ticket.status]}
                            </Badge>
                            <small>
                              {ticket.firstResponseAt
                                ? 'First response recorded'
                                : 'No first response'}
                            </small>
                          </TableCell>
                          <TableCell>
                            <b
                              className={
                                ticket.overdueHours ? 'text-danger' : ''
                              }
                            >
                              {ticket.overdueHours
                                ? `${ticket.overdueHours.toFixed(1)}h overdue`
                                : 'Within SLA'}
                            </b>
                            <small>Due {formatStamp(ticket.dueAt)}</small>
                          </TableCell>
                          <TableCell>
                            <b>
                              {ticket.customer.valueTier} /{' '}
                              {ticket.customer.riskLevel}
                            </b>
                            <small>
                              {ticket.customer.valueScore} /{' '}
                              {ticket.customer.riskScore}
                            </small>
                          </TableCell>
                          <TableCell>
                            <span className="owner-chip">
                              {ticket.ownerRole}
                            </span>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {!filteredComplaints.length && (
                  <EmptyState text="No complaints match the filters." />
                )}
              </section>
            </>
          )}

          {page === 'resolution' && (
            <>
              <section className="case-selector">
                <div className="case-field">
                  <span>Complaint to investigate</span>
                  <Select
                    value={resolutionTicketId}
                    onValueChange={(value) => {
                      if (value) {
                        setResolutionTicketId(value);
                        setSelectedResolutionId('');
                      }
                    }}
                    items={data.complaints.map((ticket) => ({
                      value: ticket.id,
                      label: `${ticket.id} · ${ticket.issue}`,
                    }))}
                  >
                    <SelectTrigger aria-label="Complaint to investigate">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {data.complaints.map((ticket) => (
                        <SelectItem key={ticket.id} value={ticket.id}>
                          {ticket.id} · {ticket.issue}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <span>Priority</span>
                  <b>{investigation.priority}</b>
                </div>
                <div>
                  <span>Customer</span>
                  <b>{investigation.customerId}</b>
                </div>
                <Button
                  variant="outline"
                  onClick={() => openComplaint(resolutionTicket)}
                >
                  View complaint
                </Button>
              </section>
              <section className="investigation-grid">
                <article className="panel investigation-card">
                  <div className="panel-head">
                    <div>
                      <p className="eyebrow">ORDER + OPERATIONS</p>
                      <h2>Verified timeline</h2>
                    </div>
                    <PackageCheck size={20} />
                  </div>
                  <div className="timeline-list">
                    {investigation.timeline.map((event) => (
                      <div key={event.label}>
                        <span
                          className={`evidence-tag ${event.kind.replaceAll(' ', '-').toLowerCase()}`}
                        >
                          {event.kind}
                        </span>
                        <b>{event.label}</b>
                        <small>
                          {event.at || 'Not available'} · {event.detail}
                        </small>
                      </div>
                    ))}
                  </div>
                </article>
                <article className="panel investigation-card">
                  <div className="panel-head">
                    <div>
                      <p className="eyebrow">INVENTORY</p>
                      <h2>Replacement check</h2>
                    </div>
                    <PackageCheck size={20} />
                  </div>
                  <div className="impact-body">
                    <span className="evidence-tag demo-assumption">
                      Demo assumption
                    </span>
                    <strong>
                      {investigation.inventory.availableUnits} units
                    </strong>
                    <p>{investigation.inventory.replacementSku}</p>
                    <dl>
                      <div>
                        <dt>Reserved</dt>
                        <dd>{investigation.inventory.reservedUnits}</dd>
                      </div>
                      <div>
                        <dt>Replenishment</dt>
                        <dd>
                          {investigation.inventory.replenishmentDays} days
                        </dd>
                      </div>
                    </dl>
                  </div>
                </article>
                <article className="panel investigation-card">
                  <div className="panel-head">
                    <div>
                      <p className="eyebrow">FINANCE</p>
                      <h2>Estimated exposure</h2>
                    </div>
                    <CircleDollarSign size={20} />
                  </div>
                  <div className="impact-body">
                    <span className="evidence-tag demo-assumption">
                      Demo assumption
                    </span>
                    <strong>
                      {money(investigation.financial.fullRefundExposure)}
                    </strong>
                    <p>Full refund exposure</p>
                    <dl>
                      <div>
                        <dt>Replacement</dt>
                        <dd>
                          {money(
                            investigation.financial.replacementCostEstimate,
                          )}
                        </dd>
                      </div>
                      <div>
                        <dt>Service credit</dt>
                        <dd>
                          {money(investigation.financial.serviceCreditEstimate)}
                        </dd>
                      </div>
                    </dl>
                  </div>
                </article>
              </section>
              <section className="recommendation-banner">
                <Bot size={22} />
                <div>
                  <p className="eyebrow">AGENT RECOMMENDATION</p>
                  <h2>{investigation.recommendation.label}</h2>
                  <p>{investigation.rationale}</p>
                </div>
                <span>Human approval required</span>
              </section>
              <section className="option-grid">
                {options.map((option) => (
                  <button
                    type="button"
                    key={option.id}
                    disabled={!option.feasible}
                    className={`option-card ${selectedResolution.id === option.id ? 'selected' : ''}`}
                    onClick={() => setSelectedResolutionId(option.id)}
                  >
                    <div>
                      <span>
                        {option.recommended
                          ? 'Recommended'
                          : option.feasible
                            ? 'Available'
                            : 'Unavailable'}
                      </span>
                      <b>{option.label}</b>
                    </div>
                    <strong>{money(option.estimatedCost)}</strong>
                    <dl>
                      <div>
                        <dt>Resolution time</dt>
                        <dd>{option.resolutionDays} days</dd>
                      </div>
                      <div>
                        <dt>Relationship recovery</dt>
                        <dd>{option.relationshipRecovery}</dd>
                      </div>
                    </dl>
                    <p>{option.conditions}</p>
                    <small>{option.risk}</small>
                  </button>
                ))}
              </section>
              <section className="decision-bar">
                <div>
                  <b>Selected: {selectedResolution.label}</b>
                  <p>
                    {money(selectedResolution.estimatedCost)} estimated cost ·
                    no action will execute automatically.
                  </p>
                </div>
                <Button
                  onClick={() =>
                    submitForApproval(resolutionTicket, selectedResolution)
                  }
                  disabled={!selectedResolution.feasible}
                >
                  Submit for human approval
                  <ChevronRight size={16} />
                </Button>
              </section>
              <section className="score-note">
                <ShieldCheck size={20} />
                <div>
                  <b>Decision boundary</b>
                  <p>
                    {investigation.boundary} The recommendation is deterministic
                    and must be reviewed before use.
                  </p>
                </div>
              </section>
            </>
          )}

          {page === 'approvals' && (
            <section className="panel followup-panel">
              <div className="panel-head">
                <div>
                  <p className="eyebrow">HUMAN CONTROL</p>
                  <h2>Resolution approvals and audit trail</h2>
                </div>
                <span>{followups.length} local record(s)</span>
              </div>
              <p className="panel-intro">
                Agent proposals start in Pending Review. A human can approve or
                reject them. Approved proposals must move through In Progress
                before Completed. This prototype does not call external systems.
              </p>
              <div className="approval-note">
                <Input
                  value={approvalNote}
                  onChange={(event) => setApprovalNote(event.target.value)}
                  placeholder="Optional reviewer note"
                  aria-label="Reviewer note"
                />
              </div>
              <div className="followup-list">
                {followups.map((item) => (
                  <article className="followup-card" key={item.id}>
                    <div className="followup-top">
                      <span
                        className={`status-dot status-${item.status.replaceAll(' ', '-').toLowerCase()}`}
                      />
                      <div>
                        <b>
                          {item.complaintId} · {item.resolutionLabel}
                        </b>
                        <small>
                          {item.customerId} · Owner: {item.owner} · Estimated{' '}
                          {money(item.estimatedCost)}
                        </small>
                      </div>
                      <span className="followup-status">{item.status}</span>
                    </div>
                    <div className="followup-body">
                      <div>
                        <span>CUSTOMER REPLY DRAFT</span>
                        <p>{item.replyDraft}</p>
                      </div>
                      <div>
                        <span>INTERNAL HANDOFF</span>
                        <p>{item.internalDraft}</p>
                      </div>
                    </div>
                    <details className="audit-log">
                      <summary>
                        Audit trail · {item.audit.length} event(s)
                      </summary>
                      {item.audit.map((entry) => (
                        <p key={`${entry.at}-${entry.action}`}>
                          <b>{entry.action}</b> · {entry.actor} ·{' '}
                          {formatStamp(entry.at)}
                          <span>{entry.note}</span>
                        </p>
                      ))}
                    </details>
                    <div className="followup-actions">
                      <small>Due: {formatStamp(item.due)}</small>
                      <div>
                        {item.status === 'Pending Review' && (
                          <>
                            <Button
                              variant="outline"
                              onClick={() => transition(item, 'Rejected')}
                            >
                              Reject
                            </Button>
                            <Button
                              onClick={() => transition(item, 'Approved')}
                            >
                              Approve
                            </Button>
                          </>
                        )}
                        {item.status === 'Approved' && (
                          <Button
                            onClick={() => transition(item, 'In Progress')}
                          >
                            Start work
                          </Button>
                        )}
                        {item.status === 'In Progress' && (
                          <Button onClick={() => transition(item, 'Completed')}>
                            Mark completed
                          </Button>
                        )}
                        {item.status === 'Completed' && (
                          <span className="done">
                            <Check size={15} />
                            Completed; outcome awaits future data
                          </span>
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
              {!followups.length && (
                <EmptyState text="No proposals yet. Select a complaint in the Resolution Lab and submit an option for review." />
              )}
            </section>
          )}
        </main>
      </SidebarInset>

      <Sheet
        open={!!selectedCustomer}
        onOpenChange={(open) => !open && setSelectedCustomer(null)}
      >
        <SheetContent className="detail-sheet">
          <SheetHeader>
            <SheetDescription>
              Customer 360 · Olist facts and CRM replay
            </SheetDescription>
            <SheetTitle>{selectedCustomer?.name}</SheetTitle>
          </SheetHeader>
          {selectedCustomer && (
            <>
              <div className="profile-scores">
                <div>
                  <span>Customer value</span>
                  <strong>{selectedCustomer.valueScore}</strong>
                  <i
                    className={`tier ${tierClass(selectedCustomer.valueTier)}`}
                  >
                    {selectedCustomer.valueTier}
                  </i>
                </div>
                <div>
                  <span>Relationship risk</span>
                  <strong>{selectedCustomer.riskScore}</strong>
                  <i
                    className={`risk-label ${riskClass(selectedCustomer.riskLevel)}`}
                  >
                    {selectedCustomer.riskLevel}
                  </i>
                </div>
              </div>
              <section className="detail-section">
                <h3>Score evidence</h3>
                {selectedCustomer.scoreReasons.map((reason) => (
                  <p className="reason-row" key={reason}>
                    <Check size={15} />
                    {reason}
                  </p>
                ))}
              </section>
              <section className="detail-section">
                <h3>Next action</h3>
                <p>{selectedCustomer.nextAction}</p>
              </section>
              <section className="detail-section">
                <h3>Profile</h3>
                <dl className="detail-list">
                  <div>
                    <dt>Location</dt>
                    <dd>
                      {selectedCustomer.city}, {selectedCustomer.state}
                    </dd>
                  </div>
                  <div>
                    <dt>Orders</dt>
                    <dd>{selectedCustomer.orderCount}</dd>
                  </div>
                  <div>
                    <dt>Total payment</dt>
                    <dd>{money(selectedCustomer.spend)}</dd>
                  </div>
                  <div>
                    <dt>Average review</dt>
                    <dd>
                      {selectedCustomer.averageReviewScore?.toFixed(1) ??
                        'Not available'}
                    </dd>
                  </div>
                </dl>
              </section>
            </>
          )}
        </SheetContent>
      </Sheet>

      <Sheet
        open={!!selectedComplaint}
        onOpenChange={(open) => !open && setSelectedComplaint(null)}
      >
        <SheetContent className="detail-sheet">
          <SheetHeader>
            <SheetDescription>Complaint investigation</SheetDescription>
            <SheetTitle>
              {selectedComplaint?.id} · {selectedComplaint?.priorityLevel}
            </SheetTitle>
          </SheetHeader>
          {selectedComplaint && (
            <>
              <div className="ticket-heading">
                <span
                  className={`priority-badge p-${selectedComplaint.priorityLevel}`}
                >
                  {selectedComplaint.priorityScore}
                </span>
                <div>
                  <b>{selectedComplaint.issue}</b>
                  <p>
                    {selectedComplaint.customer.name} ·{' '}
                    {selectedComplaint.orderId}
                  </p>
                </div>
              </div>
              <section className="detail-section">
                <h3>Priority evidence</h3>
                {selectedComplaint.reasons.map((reason) => (
                  <p className="reason-row" key={reason}>
                    <Check size={15} />
                    {reason}
                  </p>
                ))}
              </section>
              <section className="detail-section action-box">
                <h3>Next best action</h3>
                <p>{selectedComplaint.nextAction}</p>
              </section>
              <section className="detail-section">
                <label htmlFor="reply-draft">Customer reply draft</label>
                <Textarea
                  id="reply-draft"
                  value={replyDraft}
                  onChange={(event) => setReplyDraft(event.target.value)}
                />
              </section>
              <section className="detail-section">
                <label htmlFor="internal-draft">Internal handoff draft</label>
                <Textarea
                  id="internal-draft"
                  value={internalDraft}
                  onChange={(event) => setInternalDraft(event.target.value)}
                />
              </section>
              <div className="sheet-actions">
                <Button
                  variant="outline"
                  onClick={() => setSelectedComplaint(null)}
                >
                  Close
                </Button>
                <Button onClick={() => openResolutionLab(selectedComplaint)}>
                  Investigate options
                  <ChevronRight size={16} />
                </Button>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
      <CrmAgentPanel />
    </SidebarProvider>
  );
}
