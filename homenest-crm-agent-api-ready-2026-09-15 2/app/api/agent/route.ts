import { crmTools, demoAgentAnswer, type AgentToolCall } from '@/lib/agent';
import { runCrmToolWithBackend } from '@/lib/team-backend';

const instructions = `You are the HomeNest CRM service recovery agent.
Help service managers identify relationship risk, investigate complaints across CRM, fulfilment, inventory and finance, compare resolution options, and prepare drafts for human review.
Every customer, complaint, score, date and amount must come from tool results. Never invent business facts.
Customer value and relationship risk are not credit ratings. Never use sensitive personal attributes.
Olist facts, CRM replay fields and demo assumptions must remain visibly distinct.
All replies and proposed resolutions are drafts. Never claim that a customer was contacted, a refund was issued, an item was shipped or a business record was changed.
Answer in concise English. Lead with the recommendation, then give evidence, assumptions and required approval.`;

type ResponseItem = {
  type: string;
  name?: string;
  arguments?: string;
  call_id?: string;
  content?: Array<{ type: string; text?: string }>;
};

const responseText = (body: {
  output?: ResponseItem[];
  output_text?: string;
}) =>
  body.output_text ||
  (body.output || [])
    .filter((item) => item.type === 'message')
    .flatMap((item) => item.content || [])
    .filter((item) => item.type === 'output_text' && item.text)
    .map((item) => item.text)
    .join('\n');

async function callOpenAI(apiKey: string, input: unknown[]) {
  const response = await fetch('https://api.openai.com/v1/responses', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: process.env.OPENAI_MODEL || 'gpt-5.6',
      instructions,
      input,
      tools: crmTools,
      tool_choice: 'auto',
      store: false,
    }),
  });
  const body = (await response.json()) as {
    error?: { message?: string };
    output?: ResponseItem[];
    output_text?: string;
  };
  if (!response.ok)
    throw new Error(
      body.error?.message || `OpenAI API returned ${response.status}`,
    );
  return body;
}

export async function POST(request: Request) {
  const body = (await request.json().catch(() => ({}))) as {
    question?: unknown;
  };
  const question =
    typeof body.question === 'string' ? body.question.trim() : '';
  if (!question)
    return Response.json(
      { error: 'Enter a customer relationship question.' },
      { status: 400 },
    );
  if (question.length > 800)
    return Response.json(
      { error: 'Keep the question under 800 characters.' },
      { status: 400 },
    );

  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    const demo = demoAgentAnswer(question);
    return Response.json({
      ...demo,
      mode: 'demo',
      note: 'OPENAI_API_KEY is not configured; using the deterministic tool demo.',
    });
  }

  try {
    const input: unknown[] = [{ role: 'user', content: question }];
    const toolCalls: AgentToolCall[] = [];
    let response = await callOpenAI(apiKey, input);

    for (let turn = 0; turn < 4; turn += 1) {
      const calls = (response.output || []).filter(
        (item) => item.type === 'function_call',
      );
      input.push(...(response.output || []));
      if (!calls.length)
        return Response.json({
          answer: responseText(response) || 'The agent returned no text.',
          toolCalls,
          mode: 'llm',
        });

      for (const call of calls) {
        if (!call.name || !call.call_id) continue;
        let args: Record<string, unknown> = {};
        try {
          args = JSON.parse(call.arguments || '{}') as Record<string, unknown>;
        } catch {
          args = {};
        }
        const execution = await runCrmToolWithBackend(call.name, args);
        const result = execution.result;
        toolCalls.push({
          name: call.name,
          arguments: args,
          resultSummary: Array.isArray(result)
            ? `Returned ${result.length} record(s) from ${execution.source}`
            : result && typeof result === 'object' && 'error' in result
              ? String(result.error)
              : `Returned one grounded result from ${execution.source}`,
        });
        input.push({
          type: 'function_call_output',
          call_id: call.call_id,
          output: JSON.stringify(result),
        });
      }
      response = await callOpenAI(apiKey, input);
    }
    return Response.json(
      {
        error: 'The agent exceeded the tool-call limit. Narrow the question.',
        toolCalls,
      },
      { status: 422 },
    );
  } catch (error) {
    return Response.json(
      {
        error:
          error instanceof Error ? error.message : 'The agent request failed.',
      },
      { status: 502 },
    );
  }
}
