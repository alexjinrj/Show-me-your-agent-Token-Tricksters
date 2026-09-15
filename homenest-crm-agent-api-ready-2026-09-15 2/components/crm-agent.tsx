'use client';

import { useState } from 'react';
import {
  Bot,
  ChevronDown,
  CircleAlert,
  Send,
  Sparkles,
  Wrench,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

type ToolCall = {
  name: string;
  arguments: Record<string, unknown>;
  resultSummary: string;
};
type Message = {
  role: 'user' | 'agent';
  text: string;
  mode?: 'llm' | 'demo';
  tools?: ToolCall[];
};

const examples = [
  'Who should we contact first?',
  'Investigate TKT-004 and recommend the best action',
  'Compare resolution options for TKT-009',
  'Draft a reply for TKT-014',
];

const toolLabels: Record<string, string> = {
  list_priority_complaints: 'Read priority queue',
  get_customer_360: 'Read Customer 360',
  get_complaint_detail: 'Read complaint details',
  get_order_timeline: 'Trace order timeline',
  get_inventory_availability: 'Check replacement inventory',
  estimate_refund_impact: 'Estimate financial impact',
  compare_resolution_options: 'Compare resolution options',
  recommend_resolution: 'Recommend resolution',
  draft_customer_reply: 'Draft customer reply',
  create_followup_proposal: 'Create approval proposal',
};

export function CrmAgentPanel() {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'agent',
      text: 'I can prioritise complaints, investigate order and delivery evidence, check assumed replacement inventory, compare financial impact and prepare a resolution for human approval.',
    },
  ]);

  const ask = async (value = question) => {
    const prompt = value.trim();
    if (!prompt || loading) return;
    setQuestion('');
    setLoading(true);
    setMessages((current) => [...current, { role: 'user', text: prompt }]);
    try {
      const response = await fetch('/api/agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: prompt }),
      });
      const data = (await response.json()) as {
        answer?: string;
        error?: string;
        mode?: 'llm' | 'demo';
        toolCalls?: ToolCall[];
      };
      setMessages((current) => [
        ...current,
        {
          role: 'agent',
          text: data.answer || data.error || 'No answer is available.',
          mode: data.mode,
          tools: data.toolCalls,
        },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          role: 'agent',
          text: 'The agent endpoint is temporarily unavailable.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Button
        className="agent-launcher"
        onClick={() => setOpen(true)}
        aria-label="Open CRM Agent"
      >
        <Sparkles size={17} />
        Ask CRM Agent
      </Button>
      {open && (
        <section className="agent-panel" aria-label="CRM Agent chat">
          <header>
            <div className="agent-avatar">
              <Bot size={20} />
            </div>
            <div>
              <b>CRM Agent</b>
              <small>Cross-functional tools · human approval</small>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close CRM Agent">
              <X size={18} />
            </button>
          </header>
          <div className="agent-messages">
            {messages.map((message, index) => (
              <article
                className={`agent-message ${message.role}`}
                key={`${message.role}-${index}`}
              >
                {message.role === 'agent' && (
                  <span className="message-author">
                    <Bot size={14} />
                    Agent{' '}
                    {message.mode === 'llm'
                      ? '· LLM'
                      : message.mode === 'demo'
                        ? '· deterministic demo'
                        : ''}
                  </span>
                )}
                <p>{message.text}</p>
                {!!message.tools?.length && (
                  <details className="tool-trace">
                    <summary>
                      <Wrench size={13} />
                      View tool trace
                      <ChevronDown size={13} />
                    </summary>
                    {message.tools.map((tool, toolIndex) => (
                      <div key={`${tool.name}-${toolIndex}`}>
                        <b>{toolLabels[tool.name] || tool.name}</b>
                        <small>
                          {Object.keys(tool.arguments).length
                            ? JSON.stringify(tool.arguments)
                            : 'No arguments'}{' '}
                          · {tool.resultSummary}
                        </small>
                      </div>
                    ))}
                  </details>
                )}
              </article>
            ))}
            {loading && (
              <article className="agent-message agent loading-message">
                <span />
                <span />
                <span />
              </article>
            )}
          </div>
          {messages.length === 1 && (
            <div className="agent-examples">
              {examples.map((example) => (
                <button key={example} onClick={() => ask(example)}>
                  {example}
                </button>
              ))}
            </div>
          )}
          <form
            className="agent-input"
            onSubmit={(event) => {
              event.preventDefault();
              ask();
            }}
          >
            <Input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              maxLength={800}
              placeholder="Try: investigate TKT-004"
              aria-label="Ask CRM Agent"
            />
            <Button
              type="submit"
              size="icon"
              disabled={!question.trim() || loading}
              aria-label="Send question"
            >
              <Send size={16} />
            </Button>
          </form>
          <footer>
            <CircleAlert size={13} />
            Facts, replay fields and assumptions remain labelled. Actions
            require human approval.
          </footer>
        </section>
      )}
    </>
  );
}
