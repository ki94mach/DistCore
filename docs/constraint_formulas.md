# Optimization Model: Complete Constraint Formulas

## Notation

- **x[d,p]**: Decision variable - shipment quantity from factory to distributor `d` for product `p` (x[d,p] ≥ 0)
- **Inv[d,p]**: Inventory on-hand at distributor `d` for product `p`
- **FactoryInv[p]**: Factory inventory/supply available for product `p`
- **DelMA₆[d,p]**: 6-month moving average of *monthly* historical delivery totals to distributor `d` for product `p` (average of per-month SUMs over the last 6 Jalali months)
- **SalesMA_k[d,p]**: k-month moving average of sales (k ∈ {3,6}, configurable via `SalesWindow`)
- **SalesMTD[d,p]**: Sales month-to-date at distributor `d` for product `p`
- **TargetUnits[p]**: Target units for product `p`
- **TotalSalesMTD[p]**: Total sales month-to-date across all distributors for product `p`
- **RemainingTargetUnits[p]**: `max(0, TargetUnits[p] - TotalSalesMTD[p])`
- **HasDeliveryLast6M[d,p]**: Binary indicator (0 or 1) - whether distributor `d` had delivery of product `p` in last 6 months

### Parameters (from OptimizationSettings)

- **CoverageRatio**: Multiplier for demand coverage (SC1) vs CoverageDemand (default: 1.5)
- **TargetCoverageRatio**: Multiplier for target units coverage (SC2) (default: 1.5)
- **DeliveryLowerBound**: Minimum delivery as fraction of 6-month delivery average (default: 0.9)
- **DeliveryUpperBound**: Maximum delivery as fraction of 6-month delivery average (default: 1.2)
- **weight_demand**: Objective weight for demand coverage slack (default: 1.0)
- **weight_target_units**: Objective weight for target-units slack (default: 2.0)
- **weight_smoothing**: Objective weight for delivery smoothing slack (default: 1.0)
- **weight_shipment**: Objective weight for decision variables - shipment regularization (default: 1.0)

### Slack Variables

- **s_demand_coverage[d,p] ≥ 0**: Shortfall in distributor/product coverage
- **s_units[p] ≥ 0**: Shortfall in total unit coverage against target units
- **s_delivery_low[d,p] ≥ 0**: Deviation below historical delivery lower bound
- **s_delivery_high[d,p] ≥ 0**: Deviation above historical delivery upper bound

---

## Hard Constraints (Must Never Be Violated)

### HC1 – Factory Supply Feasibility
**Constraint Type**: `FactorySupplyConstraint` (Hard)

For every product `p`:

```
Σ_d x[d,p] ≤ FactoryInv[p]
```

**In words**: Total shipments across all distributors for product `p` cannot exceed factory inventory/supply.

**Number of constraints**: One per product (P constraints total)

---

### HC2 – No Delivery Without Historical Activity
**Constraint Type**: `DeliveryHistoryConstraint` (Hard)

For every distributor `d` and product `p` where `HasDeliveryLast6M[d,p] = 0`:

```
x[d,p] ≤ 0
```

Since x[d,p] ≥ 0 (non-negativity), this effectively means:

```
x[d,p] = 0
```

**In words**: If a distributor had no delivery of a product in the last 6 months, no shipment is allowed.

**Number of constraints**: One per distributor-product pair without recent delivery (M constraints, where M ≤ D×P)

---

### HC3 – Non-Negativity
**Constraint Type**: Enforced via variable bounds (Hard)

For every distributor `d` and product `p`:

```
x[d,p] ≥ 0
```

**In words**: Shipment quantities cannot be negative.

**Implementation**: Enforced via variable lower bounds (`low=0.0`), not as explicit constraints.

---

## Soft Constraints (Allowed to Violate With Penalty)

### SC1 – Distributor-Product Coverage vs Sales (Demand-Based)
**Constraint Type**: `DemandCoverageConstraint` (Soft)

For every distributor `d` and product `p`:

```
Inv[d,p] + x[d,p] + s_demand_coverage[d,p] ≥ CoverageRatio × CoverageDemand[d,p]
```

Where:
```
CoverageDemand[d,p] = max(0, SalesMA_k[d,p] - SalesMTD[d,p])
```

**In words**: Each distributor's on-hand inventory plus shipment plus slack must cover at least `CoverageRatio` times the remaining demand (sales moving average minus month-to-date sales).

**Slack penalty in objective**: `weight_demand × s_demand_coverage[d,p]`

**Number of constraints**: One per distributor-product pair (D×P constraints total)

---

### SC2 – Total Product Coverage vs Target Units
**Constraint Type**: `ProductTargetUnitsConstraint` (Soft)

For every product `p`:

```
Σ_d (Inv[d,p] + x[d,p]) + s_units[p] ≥ TargetCoverageRatio × RemainingTargetUnits[p]
```

Where:
```
RemainingTargetUnits[p] = max(0, TargetUnits[p] - TotalSalesMTD[p])
```

**In words**: Total inventory across all distributors plus total shipments plus slack must cover at least `TargetCoverageRatio` times the remaining target units.

**Slack penalty in objective**: `weight_target_units × s_units[p]`

**Number of constraints**: One per product (P constraints total)

---

### SC5 – Delivery Smoothing vs Historical Deliveries
**Constraint Type**: `DeliverySmoothingConstraint` (Soft)

For every distributor `d` and product `p`:

#### Lower Bound:
```
x[d,p] + s_delivery_low[d,p] ≥ EffectiveLowerBound[d,p]
```

Where:
```
EffectiveLowerBound[d,p] = {
    DeliveryLowerBound × DelMA₆[d,p]  if (CoverageDemand[d,p] > 0 OR RemainingTargetUnits[p] > 0)
    0                                  otherwise
}
```

**In words**: Shipment should be at least `DeliveryLowerBound` times the 6-month delivery moving average, but only if there is demand or remaining target. Otherwise, no forced shipment (lower bound = 0).

#### Upper Bound:
```
x[d,p] - s_delivery_high[d,p] ≤ DeliveryUpperBound × DelMA₆[d,p]
```

**In words**: Shipment should not exceed `DeliveryUpperBound` times the 6-month delivery moving average.

**Slack penalties in objective**: 
- `weight_smoothing × s_delivery_low[d,p]`
- `weight_smoothing × s_delivery_high[d,p]`

**Number of constraints**: Two per distributor-product pair (2×D×P constraints total)

---

## Objective Function

The model minimizes the following objective:

```
minimize: 
    Σ_d Σ_p weight_shipment × x[d,p]
  + Σ_d Σ_p weight_demand × s_demand_coverage[d,p]
  + Σ_p weight_target_units × s_units[p]
  + Σ_d Σ_p weight_smoothing × s_delivery_low[d,p]
  + Σ_d Σ_p weight_smoothing × s_delivery_high[d,p]
```

**In words**: Minimize total shipment (regularization) plus penalties for:
- Demand coverage shortfalls
- Target units shortfalls
- Delivery smoothing violations (both below lower bound and above upper bound)

**Note**: `ShipmentMinimizationConstraint` adds the first term (shipment regularization) to the objective. This acts as a tiebreaker when multiple solutions satisfy soft constraints equally well.

---

## Summary of Constraint Counts

For a problem with:
- **D** distributors
- **P** products
- **M** distributor-product pairs without recent delivery (M ≤ D×P)

**Total constraints**:
- **Hard constraints**: P + M (factory supply + delivery history)
- **Soft constraints**: D×P + P + 2×D×P = 3×D×P + P
  - Demand coverage: D×P
  - Target units: P
  - Delivery smoothing: 2×D×P (lower + upper bounds)

**Grand total**: P + M + 3×D×P + P = **M + 3×D×P + 2×P** constraints

**Example**: For "Lyratan" with ~40 distributors:
- Factory supply: 1
- Delivery history: ~M (varies)
- Demand coverage: ~40
- Target units: 1
- Delivery smoothing: ~80 (40 × 2)
- **Total**: ~122-124 constraints (matches your observation!)

---

## Constraint Relationships

1. **Factory Supply (HC1)** limits the sum of all shipments for a product
2. **Delivery History (HC2)** prevents shipments to inactive distributor-product pairs
3. **Demand Coverage (SC1)** encourages sufficient inventory at each distributor
4. **Target Units (SC2)** encourages sufficient total inventory across all distributors
5. **Delivery Smoothing (SC5)** keeps shipments consistent with historical patterns
6. **Shipment Minimization** (in objective) discourages unnecessary shipments

All constraints work together to find an optimal allocation that:
- Respects factory capacity
- Only ships to active distributor-product pairs
- Meets demand and target coverage goals
- Maintains delivery consistency
- Minimizes unnecessary shipments
