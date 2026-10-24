# Skill: Simulation Scenario Design

## Purpose
Design and run business simulation scenarios to evaluate policy interventions.

## When to Use
- User wants to test "what-if" scenarios
- User wants to compare intervention strategies
- User wants to forecast impact of changes

## Steps
1. Call `domain.models` to understand simulation state structure
2. Call `tools.simulation.engine.run_simulation()` with scenario configuration
3. Define events: `ScenarioEvent` (type, timestamp, parameters)
4. Run base simulation (no intervention) as baseline
5. Run intervention simulation with events
6. Compare results using `tools.simulation.state` utilities

## Tool Dependencies
- domain.models
- tools.simulation.engine
- tools.simulation.scenarios
- tools.simulation.state

## Output Format
- Baseline metrics vs intervention metrics
- Delta analysis (improvement, degradation)
- Confidence indicators (result_hash for reproducibility)

## Constraints
- Identical inputs must produce identical results
- Calculations performed by Python, not LLM
- Use deterministic seed for reproducibility
- Result hash must be verified
