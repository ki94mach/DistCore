# Production migrations

Run against the prod database on the source server (`db.yml` → `prod` connection).

Included scripts (in order):

- `000_init_schemas.sql`
- `010_ctl_batchrun.sql`
- `030_snap_factory_inventory_snapshot.sql`
- `031_snap_distributor_inventory_snapshot.sql`
- `032_snap_sales_snapshot.sql`
- `033_snap_target_snapshot.sql`
- `034_snap_distributor_deliveries_snapshot.sql`
- `036_fact_distributor_deliveries.sql`

**Not included:** `020`–`024` staging migrations, `035` staging default update.

Execute via:

```bash
python scripts/migrations.py --prod
```
