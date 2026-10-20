# SOP-211: Top-ups, refunds, adjustments, balances and statements
**Status:** commands tested 2026-10-20 (live tests with the test customers). First real use: the first customer.

## Purpose
The day-to-day money tasks. Each command runs `cluster-billing` on anton and is logged (SOP-001). Every change is a new ledger entry; nothing is ever edited or deleted. Amounts are in credits (1 credit = 1 US dollar, plan D40).

## Commands
| Task | Command |
|---|---|
| Record a payment | `./cluster credits topup c4821 500 --ref INV-1042 [--note "..."]`. **The reference must be the invoice number:** the same reference is never counted twice, so running it again by mistake changes nothing. The credit expires 12 months from today. |
| Give credit | `./cluster credits grant c4821 20 --ref GOODWILL-7 --note "outage 2026-11-03"`. For goodwill or promotions; there are no free trials (D43). Test customers get test credit this way. |
| Correct a mistake | `./cluster credits adjust c4821 -12.50 --ref ADJ-7 --note "why"`. Positive adds credit, negative takes it. A note is required. |
| Refund a job | `./cluster credits refund <DBIndex> --reason "..."`. Find the DBIndex with `sudo sacct -D -j <jobid> -o DBIndex,JobID,State`. Node failures are refunded automatically. |
| Balances | `./cluster credits balance [c4821]`: available credit, unpaid charges, and each batch with its expiry date. |
| Statement | `./cluster credits statement c4821 2026-10 [--json]`: opening balance, top-ups, grants, refunds, adjustments, compute, storage, expired, closing balance, then every entry. |
| Run billing now | `./cluster credits hourly`. Normally the timer does it every hour. |

## Before you start
- For a top-up: the payment has arrived. Have the customer code and the invoice number.

## Checks
- `./cluster credits balance <customer>` shows the new amount.
- `sudo scontrol show assoc_mgr flags=qos qos=cust-<code>`: after the next sync, the `billing=` limit has gone up by what the credit buys.

## If something goes wrong
- **"Already recorded … Nothing changed":** that reference was used before. If it's really a second payment, use its own invoice number.
- **A top-up for the wrong customer:** add `adjust <wrong> -<amount> --ref <ref>-REVERSAL --note "..."`, then the top-up for the right customer with the real reference.

## History
- 2026-10-20: commands written and tested with the test customers.
