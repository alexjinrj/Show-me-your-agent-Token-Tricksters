# Skill: Sales Analysis

## Purpose
Analyze sales backlog, identify bottlenecks, and recommend interventions.

## When to Use
- User asks about sales orders, backlog, revenue, or delivery issues
- User wants to diagnose why orders are delayed
- User wants to compare sales performance across time periods

## Steps
1. Call `tools.analysis_tool.tools.get_actual_state_summary()` to get current sales data
2. Call `tools.analysis_tool.tools.list_exceptions()` to identify backlog exceptions
3. If analysis needed: call `tools.analysis_tool.analysis.AnalysisService.analyze_backlog()`
4. If simulation needed: call `tools.simulation.service.SimulationService.run_simulation()`

## Tool Dependencies
- tools.analysis_tool.tools
- tools.analysis_tool.analysis
- tools.simulation.service

## Output Format
- Summary of current state (total orders, backlog, revenue)
- Identified bottlenecks with evidence
- Recommended actions with expected impact

## Constraints
- Never fabricate data from tools
- Always cite tool_call_id when referencing tool results
- Use aggregate totals from tools verbatim
