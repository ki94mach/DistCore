# Optimization Project Description

## Project Name
Distributor Allocation Optimization (Phase 1 – Factory → Distributors)

## 1. Problem Statement
Determine optimal delivery quantities of pharmaceutical products from factories to distributors for a planning period, such that:

- Business feasibility constraints are respected (inventory, production, regulatory/business rules).
- Coverage and target expectations are met or exceeded.
- Historical behavior is respected to avoid unrealistic allocations.
- Unnecessary shipment is discouraged when constraints are already satisfied.
- The solution can evolve by adding exceptions, weights, and expiry logic.

This phase focuses only on factory → distributor allocation (not distributor → centers).

## 2. Sets, Indices, and Notation
- **P**: set of products
- **D**: set of distributors
- **F**: set of factories
- **T**: planning period (single period for now)

**Mappings**
- **FactoryOf(p) ∈ F**: factory producing product _p_

**Notation conventions**
- **Σ_d** means "sum over all distributors _d ∈ D_."
- **Σ_{p ∈ f}** means "sum over products _p_ produced at factory _f_ (i.e., FactoryOf(p)=f)."
- Ratios in constraints should guard against division by zero (e.g., treat missing sales history as ineligible, or use a small ε in denominators).

## 3. Decision Variables
**Primary decision variable**
- **x[d,p] ≥ 0** (continuous): quantity of product _p_ delivered to distributor _d_ in period **T**

**Derived variables (computed, not optimized)**
- **TotalSupply[p] = Σ_d x[d,p]**
- **TotalAtDistributor[d,p] = Inv[d,p] + x[d,p]**

## 4. Input Parameters (Given Data)
**Inventory & supply**
- **Inv[d,p]**: current on-hand inventory at distributor _d_
- **FactoryInv[p]**: available factory inventory
- **ProdPlan[p]**: planned production during **T**

**Demand & history**
- **SalesMA₃[d,p]**, **SalesMA₆[d,p]**: moving average unit sales
- **SalesMTD[d,p]**: sales month-to-date
- **DelMA₆[d,p]**: 6-month moving average of historical deliveries
- **HasDeliveryLast6M[d,p] ∈ {0,1}**

**Targets**
- **TargetUnits[p]**
- **TargetValue[p]** _(planned, not yet implemented)_
- **DistributorFactoryTargetValue[d,f]** _(planned, not yet implemented)_
- **RemainingTargetValue[d,f]** _(planned, not yet implemented)_

**Prices**
- **UnitValue[p]** _(planned, not yet implemented)_

**Configuration / policy knobs** (see `OptimizationSettings` in `src/optimization/data.py`)

| Parameter | Code default | Description |
|-----------|-------------|-------------|
| **CoverageRatio** | 1 | Multiplier for target coverage vs demand |
| **SalesWindow** | 3 | Moving average window in months (3 or 6) |
| **DeliveryLowerBound** | 0.9 | Min delivery as fraction of 6‑month delivery average |
| **DeliveryUpperBound** | 1.2 | Max delivery as fraction of 6‑month delivery average |
| **weight_coverage** | 1.0 | Objective weight for coverage slack (SC1) |
| **weight_target_units** | 2.0 | Objective weight for target‑units slack (SC2) |
| **weight_smoothing** | 1.0 | Objective weight for delivery smoothing slack (SC5) |
| **weight_shipment** | 1.0 | Objective weight for decision variables — shipment regularization |

## 5. Hard Constraints (Must Never Be Violated)
These constraints define feasibility. If any of them are violated, the solution is invalid.

**HC1 – Factory supply feasibility** (`FactorySupplyConstraint`)

For every product _p_:

```
Σ_d x[d,p] ≤ FactoryInv[p]
```

> Note: the current implementation uses `FactoryInv[p]` only (no `ProdPlan[p]`). Production planning may be added in a future phase.

**HC2 – No delivery without historical activity** (`DeliveryHistoryConstraint`)

If a distributor had no delivery of a product in the last 6 months:

```
HasDeliveryLast6M[d,p] = 0 ⇒ x[d,p] = 0
```

**HC3 – Non-negativity**

```
x[d,p] ≥ 0 ∀ d,p
```

Enforced via variable lower bounds (`low=0.0`).

## 6. Soft Constraints (Allowed to Violate With Penalty)
These constraints represent business expectations. Each soft constraint is modeled with a **slack/shortfall variable** that measures how far the solution is from the target. Slack variables are then penalized in the objective.

**Slack variable conventions**
- **s\_coverage[d,p] ≥ 0**: shortfall in distributor/product coverage.
- **s\_units[p] ≥ 0**: shortfall in total unit coverage against target units.
- **s\_delivery\_low[d,p] ≥ 0**, **s\_delivery\_high[d,p] ≥ 0**: deviation below/above historical delivery bounds.

**SC1 – Distributor–product coverage vs sales (demand-based)** (`DemandCoverageConstraint`)

```
(Inv[d,p] + x[d,p]) + s_coverage[d,p] ≥ CoverageRatio × max(0, SalesMA_k[d,p] - SalesMTD[d,p])
```

Where **k ∈ {3,6}** (configurable via `SalesWindow`). This constraint encourages each distributor's on-hand + deliveries to cover a multiple of remaining demand. Uses `coverage_ratio` from `OptimizationSettings`.

**SC2 – Total product coverage vs target (units)** (`ProductTargetUnitsConstraint`)

```
Σ_d (Inv[d,p] + x[d,p]) + s_units[p] ≥ TargetCoverageRatio × RemainingTargetUnits[p]
```

Uses `target_coverage_ratio` from `OptimizationSettings`.

Where `RemainingTargetUnits[p] = max(0, TargetUnits[p] - TotalSalesMTD[p])`.

**SC3 – Total product coverage vs target (value)** _(planned, not yet implemented)_

```
Σ_d UnitValue[p] × (Inv[d,p] + x[d,p]) + s_value[p] ≥ CoverageRatio × TargetValue[p]
```

**SC4 – Factory → distributor target fulfillment (monetary)** _(planned, not yet implemented)_

If a factory-specific target exists:

```
Σ_{p ∈ f} UnitValue[p] × (Inv[d,p] + x[d,p]) + s_factory[d,f] ≥ FactoryTargetRatio × RemainingTargetValue[d,f]
```

**SC5 – Delivery smoothing vs historical deliveries** (`DeliverySmoothingConstraint`)

```
x[d,p] + s_delivery_low[d,p]  ≥ DeliveryLowerBound × DelMA_6[d,p]
x[d,p] - s_delivery_high[d,p] ≤ DeliveryUpperBound × DelMA_6[d,p]
```

The lower bound is only activated when there is positive demand or remaining target for the product; otherwise the effective lower bound is 0 (no forced shipment).

## 7. Objective Function

**Primary Objective (multi-term, weighted)**

Minimize a weighted sum of slack penalties **plus** a direct shipment regularization term:

```
min  Σ_{d,p} weight_coverage  · s_coverage[d,p]                          (SC1 penalty)
   + Σ_p     weight_target    · s_units[p]                               (SC2 penalty)
   + Σ_{d,p} weight_smoothing  · (s_delivery_low[d,p] + s_delivery_high[d,p])  (SC5 penalty)
   + Σ_{d,p} weight_shipment  · x[d,p]                                   (shipment regularization)
```

**Role of each term**

| Term | Variables | Purpose |
|------|-----------|---------|
| Coverage penalty | slack `s_coverage` | Penalize under-covering distributor demand |
| Target penalty | slack `s_units` | Penalize falling short of product targets |
| Delivery penalty | slack `s_delivery_low`, `s_delivery_high` | Penalize deviating from historical delivery patterns |
| Shipment regularization | decision `x[d,p]` | Discourage unnecessary shipping; acts as tiebreaker |

The first three terms penalize constraint violations (slack). The fourth term directly penalizes the decision variables, ensuring the solver ships only what is needed to satisfy the other constraints. Without it, the solver has no preference about shipment volume and may produce arbitrary allocations among equally-feasible solutions.

**Penalty choices**
- **Linear penalties** (as above) are transparent and easy to tune.
- **Absolute deviation** is modeled with two-sided slacks (SC5).
- **Quadratic penalties** can be used to discourage large deviations more strongly; if used, replace linear terms with quadratic costs (e.g., _w · s²_).

**Weighting guidance**
- Relative weights matter; e.g. doubling all four weights leaves the optimum unchanged.
- Increase a weight to make the solver care more about that objective (e.g., raise `weight_coverage` to prioritize filling coverage gaps).
- `weight_shipment` controls how aggressively the solver minimizes total shipping. A higher value biases toward less shipping; a lower value allows more flexibility.
- Weights can be extended to vary by distributor/product to reflect importance (e.g., high-priority products get higher weights).

## 8. Priority & Weighting Logic (Explicit Policy Layer)
Recommended default priority:

1. **HC1, HC2** – absolute feasibility
2. **SC5** – realism of deliveries
3. **SC1** – distributor coverage
4. **SC2** – product-level targets
5. **Shipment regularization** – tiebreaker among equally-feasible solutions

Weights (`weight_coverage`, `weight_target_units`, `weight_smoothing`, `weight_shipment`) are configurable via `OptimizationSettings`.

## 9. Implementation Status

| Component | Constraint class | Status |
|-----------|-----------------|--------|
| HC1 – Factory supply | `FactorySupplyConstraint` | Implemented |
| HC2 – Delivery history | `DeliveryHistoryConstraint` | Implemented |
| HC3 – Non-negativity | Variable bounds | Implemented |
| SC1 – Demand coverage | `DemandCoverageConstraint` | Implemented |
| SC2 – Target units | `ProductTargetUnitsConstraint` | Implemented |
| SC3 – Target value | — | Planned |
| SC4 – Factory→distributor target | — | Planned |
| SC5 – Delivery smoothing | `DeliverySmoothingConstraint` | Implemented |
| Shipment regularization | `ShipmentMinimizationConstraint` | Implemented |

Constraint source: `src/optimization/constraints/`

## 10. Exception & Override Mechanism (Not Optimization Logic)
The model must support:

- Product-level rule disabling (e.g., ignore **SC5** for a specific product)
- Distributor whitelists
- Rule coefficients (e.g., **CoverageRatio = 1.2** for selected products)

These are applied before optimization as parameter overrides.

## 11. Out of Scope (Planned Future Extensions)
- SC3: Value-based target coverage
- SC4: Factory→distributor monetary targets
- Expiry-date aware allocation
- Demand forecast replacing / blending **SalesMA**
- Distributor → center allocation
- Near-expiry push / liquidation logic
- Dynamic multi-period planning

## 12. Prompt-Ready Summary (One-Paragraph)
Optimize delivery quantities from factories to distributors by choosing non-negative delivery amounts per distributor and product, subject to hard constraints on factory supply and historical eligibility. Minimize a weighted combination of penalties for violating coverage ratios versus sales, product-level unit targets, deviations from historical delivery patterns, and a shipment regularization term that discourages unnecessary shipping. Treat business rules as soft constraints with configurable weights and allow product-specific exceptions via parameters.
