# Data Flow & Classification Strategy

[← Back to main README](../README.md)

Every transaction goes through two possible stages before it lands in the ledger: a fast deterministic pass, and — only if that fails — an AI pass.

## i) Deterministic Classification (DuckDB)

Most transactions never need the AI at all. Well-known merchants — POS stores, subscription services, utility companies — get matched with case-insensitive SQL rules. This is the bulk of your statement, and it's essentially instant.

Part of this stage is just cleanup: stripping marketplace prefixes like `"DD *"` or `"UBER EATS"` off the front of a description so what's left is the actual merchant underneath, not the platform that routed the payment.

## ii) AI-Powered Semantic Classification

Whatever comes out of the SQL pass still tagged `UNCLASSIFIED` gets routed to `gemini-2.5-flash`, which does the contextual/semantic reasoning that static rules can't — inferring what a merchant is from a description that doesn't match anything in the rule set.

Before any of that goes out, it's logged locally to `logs/ai_classification_audit.log`. That way there is always a record of exactly what was sent.

## Transaction Schema

Every transaction is tracked along a few different axes so you can slice the data however you need later:

- **Merchant Name** — the entity that actually received the money (`Wingstop`, not `DD *WINGSTOP ...`)
- **Category** — the broad bucket for reporting (`Groceries`, `Meals`, `Transport`, `Travel`, etc.)
- **Sub-Category** — a more specific grouping within a category (`Groceries → Grocery Delivery`, `Transport → Uber Rides`, `Transport → Public Transit`)
- **Channel** — how the transaction actually happened:
  - `pos` (in-store / point-of-sale)
  - `online` (web or app purchase, direct bill)
  - a named marketplace (`doordash`, `uber_eats`, `instacart`, etc.)
  - a financial channel (`atm`, `ach`, `p2p`)

## Processing Order: Specificity Before Generalization

Rules run top-down, most specific first, so a general rule never accidentally swallows something that should've matched something more precise earlier:

1. **Marketplace channels & prefix handling** — clean up intermediary/white-label tags before anything else runs (`"DD *WINGSTOP"` → `Wingstop`)
2. **Explicit financial types** — credit card payments, ATM withdrawals, direct transfers
3. **Digital subscriptions & streaming** — the usual suspects (Netflix, Spotify, Apple, Hulu, etc.)
4. **Standard merchants & retailers** — everything else, the general fallback rules for common brick-and-mortar and retail spend

Running things in this order is what keeps the classification reliable while still leaving room to add new vendors or transaction types later without breaking existing rules.

> **Business trips & loans** are handled as a *post-classification sidecar layer*, not as Tier 1 rules. After classification completes, the `core/pipeline.py` sidecar pipeline joins `classified_ledger` with `trips` and `cash_log` to produce the `master_ledger` view. See [Getting Started → Trip & Cash Sidecar Context](getting-started.md) for how to configure trips and manual cash/loan overrides.

---

[← Back to main README](../README.md)
