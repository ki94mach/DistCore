# Fine-Tuning the Optimization Models

This guide covers two levels of tuning: **problem settings** (constraints and objective) and **solver parameters** (e.g. Simulated Annealing).

---

## 1. Problem-level tuning: `OptimizationSettings`

These settings define the **LP problem** (constraints and objective weights). They affect all solvers.

| Parameter | Default | Where used | Effect |
|-----------|--------|------------|--------|
| **coverage_ratio** | 1.5 | Distributor coverage, target units | Target coverage = ratio × demand. Higher → ask for more stock at distributors. |
| **sales_window** | 6 | Demand calculation | 3 or 6: use 3‑month or 6‑month moving average for demand. |
| **delivery_lower_bound** | 0.9 | Delivery smoothing | Min delivery vs 6‑month average (fraction). Lower → allow smaller deliveries. |
| **delivery_upper_bound** | 1.2 | Delivery smoothing | Max delivery vs 6‑month average (fraction). Higher → allow larger spikes. |
| **weight_coverage** | 1.0 | Objective | Penalty weight for coverage slack. Increase to prioritize filling coverage gaps. |
| **weight_target_units** | 1.0 | Objective | Penalty weight for target‑units slack. Increase to prioritize hitting product targets. |
| **weight_delivery** | 1.0 | Objective | Penalty weight for delivery smoothing slack. Increase to prioritize stable deliveries. |

### How to change

- **Interactive (recommended)**  
  Run the optimization CLI and choose **“Edit these settings? (y/n)”** when prompted. You can then enter new values for each parameter.

- **In code**  
  Build an `OptimizationSettings` instance and pass it to the loader:

  ```python
  from src.optimization import OptimizationSettings, SnapshotDataLoader

  settings = OptimizationSettings(
      coverage_ratio=1.8,
      sales_window=6,
      weight_coverage=1.2,
      weight_target_units=1.0,
      weight_delivery=0.8,
  )
  # Pass settings to loader.load_optimization_data(..., settings=settings)
  ```

### Suggested tuning workflow

1. **Baseline**  
   Run with defaults; note objective value and feasibility (e.g. with `compare_solvers.py`).

2. **One parameter at a time**  
   Change a single setting (e.g. `coverage_ratio` or one weight), keep the rest fixed, then re-run and compare:
   - Objective value (lower is better for min).
   - Whether the solution stays feasible and acceptable for the business.

3. **Weights**  
   - Increase a weight if you want the model to care more about that slack (e.g. `weight_coverage` if coverage shortfalls are the main concern).
   - Relative weights matter; e.g. doubling all three weights leaves the optimum unchanged.

4. **Re-run comparisons**  
   After changing settings, run `compare_solvers.py` again on the same date to see how each solver behaves under the new problem.

---

## 2. Solver-level tuning

### Exact LP solvers (CBC, GLPK, Scipy)

No tuning parameters are exposed in the current API. They solve the same LP to optimality (within numerical tolerance). If you need time limits or tolerances, you would extend the solver adapters (e.g. PuLP/Scipy options) in `src/optimization/solver.py`.

### Greedy

No parameters. It uses a fixed rule (proportional to demand, respecting supply and delivery history).

### Simulated Annealing (SA)

SA has internal parameters that trade off **solution quality** vs **runtime**. You can tune them in two ways.

#### Option A: Pass `solver_options` when calling `solve()`

From code:

```python
from src.optimization import solve, ModelBuilder, ...  # and build model, data

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

Edit `_SAConfig` in `src/optimization/heuristic_solvers.py` to change the default values used when `solver_options` is not provided.

### Suggested SA tuning

- **Better quality, slower**: increase `max_iter` (e.g. 10000–20000), and optionally `initial_temp` or use a `cooling_rate` closer to 1 (e.g. 0.999).
- **Faster, lower quality**: decrease `max_iter` and/or use a smaller `cooling_rate` (e.g. 0.99).
- **More exploration**: increase `step_scale` slightly (e.g. 0.15); if the objective gets worse, reduce it again.

Use `compare_solvers.py` with different SA options (via a small script that calls `solve(..., solver_options=...)`) to compare objective and time.

---

## 3. Quick reference

| What you want to tune | Where | How |
|------------------------|--------|-----|
| Coverage / targets / delivery rules and weights | Problem | `OptimizationSettings` in CLI or code |
| SA quality vs speed | Solver | `solver_options["SimulatedAnnealing"]` in `solve()` or `_SAConfig` in `heuristic_solvers.py` |
| Compare after tuning | — | Same date, same settings, run `compare_solvers.py` |
