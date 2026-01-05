# Optimization Project Description

## Project Name
Distributor Allocation Optimization (Phase 1 – Factory → Distributors)

## 1. Problem Statement
Determine optimal delivery quantities of pharmaceutical products from factories to distributors for a planning period, such that:

- Business feasibility constraints are respected (inventory, production, regulatory/business rules).
- Coverage and target expectations are met or exceeded.
- Historical behavior is respected to avoid unrealistic allocations.
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
- **Σ_d** means “sum over all distributors _d ∈ D_.”
- **Σ_{p ∈ f}** means “sum over products _p_ produced at factory _f_ (i.e., FactoryOf(p)=f).”
- Ratios in constraints should guard against division by zero (e.g., treat missing sales history as ineligible, or use a small ε in denominators).

## 3. Decision Variables
**Primary decision variable**
- **x[d,p] ≥ 0** (integer or continuous): quantity of product _p_ delivered to distributor _d_ in period **T**

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
- **DelMA₆[d,p]**: 6-month moving average of historical deliveries
- **HasDeliveryLast6M[d,p] ∈ {0,1}**

**Targets**
- **TargetUnits[p]**
- **TargetValue[p]**
- **DistributorFactoryTargetValue[d,f]** (optional)
- **RemainingTargetValue[d,f]**

**Prices**
- **UnitValue[p]**

**Configuration / policy knobs**
- **CoverageRatio = 1.5**
- **FactoryTargetRatio = 1.3**
- **DeliveryLowerBound = 0.9**
- **DeliveryUpperBound = 1.2**

## 5. Hard Constraints (Must Never Be Violated)
These constraints define feasibility. If any of them are violated, the solution is invalid.

**HC1 – Factory supply feasibility**

For every product _p_:

```
Σ_d x[d,p] ≤ FactoryInv[p] + ProdPlan[p]
```

**HC2 – No delivery without historical activity**

If a distributor had no delivery of a product in the last 6 months:

```
HasDeliveryLast6M[d,p] = 0 ⇒ x[d,p] = 0
```

**HC3 – Non-negativity**

```
x[d,p] ≥ 0 ∀ d,p
```

## 6. Soft Constraints (Allowed to Violate With Penalty)
These constraints represent business expectations. Each soft constraint is modeled with a **slack/shortfall variable** that measures how far the solution is from the target. Slack variables are then penalized in the objective.

**Slack variable conventions**
- **s\_coverage[d,p] ≥ 0**: shortfall in distributor/product coverage.
- **s\_units[p] ≥ 0**: shortfall in total unit coverage against target units.
- **s\_value[p] ≥ 0**: shortfall in total value coverage against target value.
- **s\_factory[d,f] ≥ 0**: shortfall in factory→distributor target value.
- **s\_delivery\_low[d,p] ≥ 0**, **s\_delivery\_high[d,p] ≥ 0**: deviation below/above historical delivery bounds.

**SC1 – Distributor–product coverage vs sales**

```
(Inv[d,p] + x[d,p]) + s_coverage[d,p] ≥ CoverageRatio × SalesMA_k[d,p]
```

Where **k ∈ {3,6}** (configurable). This constraint encourages each distributor’s on-hand + deliveries to cover a multiple of recent sales.

**SC2 – Total product coverage vs target (units)**

```
Σ_d (Inv[d,p] + x[d,p]) + s_units[p] ≥ CoverageRatio × TargetUnits[p]
```

**SC3 – Total product coverage vs target (value)**

```
Σ_d UnitValue[p] × (Inv[d,p] + x[d,p]) + s_value[p] ≥ CoverageRatio × TargetValue[p]
```

**SC4 – Factory → distributor target fulfillment (monetary)**

If a factory-specific target exists:

```
Σ_{p ∈ f} UnitValue[p] × (Inv[d,p] + x[d,p]) + s_factory[d,f] ≥ FactoryTargetRatio × RemainingTargetValue[d,f]
```

**SC5 – Delivery smoothing vs historical deliveries**

```
DeliveryLowerBound × DelMA_6[d,p] - s_delivery_low[d,p] ≤ x[d,p]
x[d,p] ≤ DeliveryUpperBound × DelMA_6[d,p] + s_delivery_high[d,p]
```

## 7. Objective Function
**Primary Objective (multi-term, weighted)**

Minimize total penalty from violating soft constraints. The recommended formulation is a weighted sum of slack variables:

```
min  Σ_{d,p} w1[d,p] · s_coverage[d,p]
    + Σ_p   w2[p]   · s_units[p]
    + Σ_p   w2v[p]  · s_value[p]
    + Σ_{d,f} w3[d,f] · s_factory[d,f]
    + Σ_{d,p} w4[d,p] · (s_delivery_low[d,p] + s_delivery_high[d,p])
```

**Penalty choices**
- **Linear penalties** (as above) are transparent and easy to tune.
- **Absolute deviation** is modeled with two-sided slacks (SC5).
- **Quadratic penalties** can be used to discourage large deviations more strongly; if used, replace linear terms with quadratic costs (e.g., _w · s²_).

**Weighting guidance**
- Weights can vary by distributor/product to reflect importance (e.g., high-value products get higher **w₂v**).
- Consider normalizing by target sizes so weights are comparable across products.

## 8. Priority & Weighting Logic (Explicit Policy Layer)
Recommended default priority:

1. **HC1, HC2** – absolute feasibility
2. **SC5** – realism of deliveries
3. **SC1** – distributor coverage
4. **SC2 / SC3** – product-level targets
5. **SC4** – factory–distributor commercial targets

Weights (**w₁…w₄**, **w₂v**) should be configurable per product, distributor, or time period.

## 9. Exception & Override Mechanism (Not Optimization Logic)
The model must support:

- Product-level rule disabling (e.g., ignore **SC5** for Trexoma)
- Distributor whitelists
- Rule coefficients (e.g., **CoverageRatio = 1.2** for selected products)

These are applied before optimization as parameter overrides.

## 10. Out of Scope (Planned Future Extensions)
- Expiry-date aware allocation
- Demand forecast replacing / blending **SalesMA**
- Distributor → center allocation
- Near-expiry push / liquidation logic
- Dynamic multi-period planning

## 11. Prompt-Ready Summary (One-Paragraph)
Optimize delivery quantities from factories to distributors by choosing non-negative delivery amounts per distributor and product, subject to hard constraints on factory supply and historical eligibility. Minimize weighted penalties for violating coverage ratios versus sales, product-level unit and value targets, factory-specific distributor targets, and deviations from historical delivery patterns. Treat business rules as soft constraints with configurable weights and allow product-specific exceptions via parameters.
