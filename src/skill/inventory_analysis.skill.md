# Skill: Inventory Analysis

## Purpose
Analyze inventory levels, identify reorder needs, and recommend strategies.

## When to Use
- User asks about inventory levels, stockouts, or replenishment
- User wants to compare inventory strategies
- User wants to forecast demand

## Steps
1. Call `tools.inventory_tool.tools.get_actual_state_summary()` for current inventory
2. Call `tools.inventory_tool.tools.list_exceptions()` for stockout/backlog
3. Call `tools.inventory_tool.reorder.build_reorder_recommendations()` for reorder candidates
4. Call `tools.inventory_tool.strategy.run_inventory_strategy_analysis()` for strategy comparison
5. If simulation needed: call `tools.simulation.service.SimulationService.run_simulation()`

## Tool Dependencies
- tools.inventory_tool.tools
- tools.inventory_tool.reorder
- tools.inventory_tool.strategy
- tools.simulation.service

## Output Format
- Current inventory snapshot by category
- Reorder candidates with quantities and timing
- Strategy recommendations with projected impact

## Constraints
- Always use inventory position data from tools
- Never independently calculate reorder quantities
- Cite simulation result_hash for verification
