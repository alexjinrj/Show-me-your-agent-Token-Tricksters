# Skill: CRM Service Recovery

## Purpose
Handle customer complaints, draft replies, and manage service recovery workflows.

## When to Use
- User wants to respond to customer complaints
- User wants to track complaint resolution
- User needs customer communication drafts

## Steps
1. Call `tools.crm.tools.CRMAgentTools.list_complaints()` for open complaints
2. Call `tools.crm.tools.CRMAgentTools.get_complaint_details()` for specific complaint
3. Use LLM runner to draft reply (via `runtime.llm_runner.LLMRunner`)
4. Call `tools.crm.tools.CRMAgentTools.submit_reply()` to submit
5. Track resolution via `tools.crm.service.CRMService.get_resolution()`

## Tool Dependencies
- tools.crm.tools
- tools.crm.service
- runtime.llm_runner

## Output Format
- Complaint summary with severity
- Draft reply (if requested)
- Resolution timeline and next actions

## Constraints
- CRM schema_version must be "crm-api-v1"
- Explain when evidence is unavailable
- Never invent complaint history
