# Fine-Tuning the Optimization Models

This guide covers two levels of tuning: **problem settings** (constraints and objective) and **solver parameters** (e.g. Simulated Annealing).

---

## 1. Problem-level tuning: `OptimizationSettings`

These settings define the **LP problem** (constraints and objective weights). They affect all solvers.

| Parameter | Default | Where used | Effect |
|-----------|--------|------------|--------|
| **coverage_ratio** | 1 | Distributor coverage (SC1) | Distributor coverage = ratio × demand. Higher → ask for more stock at distributors. |
| **target_coverage_ratio** | 1 | Target units (SC2) | Target units coverage = ratio × remaining target. Higher → ask for more stock to meet targets. |
| **sales_window** | 3 | Demand calculation | 3 or 6: use 3‑month or 6‑month moving average for demand. |
| **delivery_lower_bound** | 0.9 | Delivery smoothing (SC5) | Min delivery vs 6‑month average (fraction). Lower → allow smaller deliveries. |
| **delivery_upper_bound** | 1.2 | Delivery smoothing (SC5) | Max delivery vs 6‑month average (fraction). Higher → allow larger spikes. |
| **weight_coverage** | 1.0 | Objective | Penalty weight for coverage slack. Increase to prioritize filling coverage gaps. |
| **weight_target_units** | 2.0 | Objective | Penalty weight for target‑units slack. Increase to prioritize hitting product targets. |
| **weight_delivery** | 1.0 | Objective | Penalty weight for delivery smoothing slack. Increase to prioritize stable deliveries. |
| **weight_shipment** | 1.0 | Objective | Weight for decision variables (shipment regularization). Increase to discourage unnecessary shipping; decrease to allow more flexibility. |

### How to change

- **Interactive (recommended)**  
  Run the optimization CLI (`scripts/optimization_cli.py`) and choose **"Edit these settings? (y/n)"** when prompted. You can then enter new values for each parameter, including `weight_shipment`.

- **In code**  
  Build an `OptimizationSettings` instance and pass it to the builder or loader:

  ```python
  from src.optimization import OptimizationSettings, SnapshotDataLoader

  settings = OptimizationSettings(
      coverage_ratio=1,
      target_coverage_ratio=1,
      sales_window=3,
      weight_coverage=1.0,
      weight_target_units=2.0,
      weight_delivery=1.0,
      weight_shipment=1.0,
  )
  # Pass settings to loader.load_optimization_data(..., settings=settings)
  # Or pass as settings_override to ModelBuilder.build(data, settings_override=settings)
  ```

### Suggested tuning workflow

1. **Baseline**  
   Run with defaults; note objective value and feasibility (e.g. with `scripts/compare_solvers.py`).

2. **One parameter at a time**  
   Change a single setting (e.g. `coverage_ratio`, `target_coverage_ratio`, or one weight), keep the rest fixed, then re-run and compare:
   - Objective value (lower is better for min).
   - Whether the solution stays feasible and acceptable for the business.

3. **Weights**  
   - Increase a weight if you want the model to care more about that term (e.g. `weight_coverage` if coverage shortfalls are the main concern).
   - `weight_shipment` controls how much the solver penalizes each unit shipped. Raise it to ship less; lower it to allow more shipping flexibility.
   - Relative weights matter; e.g. scaling all four weights by the same factor leaves the optimum unchanged.

4. **Re-run comparisons**  
   After changing settings, run `scripts/compare_solvers.py` again on the same date to see how each solver behaves under the new problem. Use `scripts/compare_parameter_presets.py` to compare multiple settings side by side.

---

## 2. Solver-level tuning

The solver layer lives in `src/optimization/solvers/`. Each solver is a subclass of `BaseSolver` (in `solvers/base.py`) with `name`, `category`, `is_available()`, and `solve()`.

### Exact LP solvers (CBC, GLPK, Scipy)

No tuning parameters are exposed in the current API. They solve the same LP to optimality (within numerical tolerance). If you need time limits or tolerances, extend the solver classes in `src/optimization/solvers/pulp_solver.py` or `src/optimization/solvers/scipy_solver.py`.

### Greedy

No parameters. It uses a fixed rule (proportional to demand, respecting supply and delivery history). Source: `src/optimization/solvers/greedy_solver.py`.

### Simulated Annealing (SA)

SA has internal parameters that trade off **solution quality** vs **runtime**. You can tune them in two ways.

#### Option A: Pass `solver_options` when calling `solve()`

From code:

```python
from src.optimization import solve

solution = solve(
    model,
    decision_variables,
    method="SimulatedAnnealing",
    data=data,
    solver_options={
        "SimulatedAnnealing": {
            "max_iter": 10000,      # more iterations → better quality, slower
            "initial_temp": 2000.0, # higher → more exploration early
            "min_temp": 0.001,      # lower → cool down more
            "cooling_rate": 0.9995, # closer to 1 → slower cooling
            "step_scale": 0.15,     # larger → bigger perturbations
        }
    },
)
```

| Parameter | Default | Effect |
|-----------|--------|--------|
| **max_iter** | 5000 | Total iterations. Increase for better solutions and longer run time. |
| **initial_temp** | 1000.0 | Starting temperature. Higher → more random acceptance at the start. |
| **min_temp** | 0.01 | Stop when temperature drops below this. |
| **cooling_rate** | 0.995 | Temperature multiplied by this each iteration. Closer to 1 → longer cooling. |
| **step_scale** | 0.1 | Perturbation size as fraction of variable range. Larger → bigger moves, noisier. |

#### Option B: Change defaults in code

Edit `SAConfig` in `src/optimization/solvers/simulated_annealing_solver.py` to change the default values used when `solver_options` is not provided.

### Suggested SA tuning

- **Better quality, slower**: increase `max_iter` (e.g. 10000–20000), and optionally `initial_temp` or use a `cooling_rate` closer to 1 (e.g. 0.999).
- **Faster, lower quality**: decrease `max_iter` and/or use a smaller `cooling_rate` (e.g. 0.99).
- **More exploration**: increase `step_scale` slightly (e.g. 0.15); if the objective gets worse, reduce it again.

Use `scripts/compare_solvers.py` with different SA options (via a small script that calls `solve(..., solver_options=...)`) to compare objective and time.

---

## 3. Objective function reference

The objective minimized by all solvers is:

```
min  weight_coverage     × Σ_{d,p} s_coverage[d,p]
   + weight_target_units × Σ_p     s_units[p]
   + weight_delivery     × Σ_{d,p} (s_delivery_low[d,p] + s_delivery_high[d,p])
   + weight_shipment     × Σ_{d,p} x[d,p]
```

| Term | Type | Controlled by |
|------|------|---------------|
| Coverage penalty | Slack | `weight_coverage` |
| Target penalty | Slack | `weight_target_units` |
| Delivery smoothing penalty | Slack | `weight_delivery` |
| Shipment regularization | Decision variable | `weight_shipment` |

The first three terms penalize soft-constraint violations. The fourth term penalizes each unit shipped, ensuring the solver does not ship more than needed.

---

## 4. Quick reference

| What you want to tune | Where | How |
|------------------------|--------|-----|
| Coverage / targets / delivery rules and weights | Problem | `OptimizationSettings` in CLI or code |
| Shipment regularization strength | Problem | `weight_shipment` in `OptimizationSettings` |
| SA quality vs speed | Solver | `solver_options["SimulatedAnnealing"]` in `solve()` or `SAConfig` in `solvers/simulated_annealing_solver.py` |
| Compare settings side by side | — | `scripts/compare_parameter_presets.py` |
| Compare solvers on same input | — | `scripts/compare_solvers.py` |

---

## 5. Architecture reference

```
src/optimization/
  data.py                 # OptimizationSettings, OptimizationData
  lp.py                   # Solver-agnostic LP model (Variable, Constraint, Model)
  builder.py              # ModelBuilder — assembles constraints into a Model
  loader.py               # SnapshotDataLoader — ETL snapshots → OptimizationData
  constraints/            # Strategy pattern: one class per constraint
    base.py               #   Constraint ABC + ConstraintResult
    factory_supply.py     #   HC1
    delivery_history.py   #   HC2
    demand_coverage.py  # SC1
    target_coverage.py    #   SC2
    delivery_smoothing.py #   SC5
    shipment.py           #   Shipment regularization
  solvers/                # Strategy pattern: one class per solver
    base.py               #   BaseSolver ABC + Solution
    pulp_solver.py        #   CBCSolver, GLPKSolver (exact)
    scipy_solver.py       #   ScipySolver (exact)
    greedy_solver.py      #   GreedySolver (heuristic)
    simulated_annealing_solver.py  # SimulatedAnnealingSolver (metaheuristic)
```
