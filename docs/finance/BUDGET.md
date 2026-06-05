# Budget & Cost-to-Serve: AI Job Matcher & CV Analyzer

**Status:** Accepted  
**Date:** 2026-06-05  
**Sources:** CONTEXT.md, docs/PRD.md, docs/security/THREAT_MODEL.md

## 1. Assumptions

| Assumption | Value | Source |
|------------|-------|--------|
| Region | **uksouth** | UK-scoped product; default until Terraform pins SKU |
| Registered users (prod) | **1–3** (mostly operator) | User confirmed — Profile A |
| Analysis Runs / month | **10–30** | User confirmed — Profile A |
| Avg listings scored per run | **40–80** (cap 100) | PRD: 50/source × 2 sources |
| Budget ceiling | **£75/month hard**; alert at **£60 (80%)** | User confirmed — Option B |
| Exceed policy | Alert + manual review; **no auto-teardown** | User confirmed |
| Idle tolerance | **Scale-to-zero** — API `minReplicas=0`, Worker `minReplicas=0` | User confirmed — Option B |
| Scaling bounds | `maxReplicas=2` (API + worker); KEDA on Service Bus queue depth | ADR-0002 + budget fit |
| Environments | **Single prod** only; local via Docker Compose | PRD out-of-scope: no paid staging |
| Email provider | Transactional (magic link + run complete); low volume | PRD |
| Currency | Estimates in **GBP**; OpenAI billed in USD (~1.27 GBP/USD for planning) |

## 2. Line-Item Cost Estimate (Monthly)

Estimates are **list-price ballpark** for uksouth (Azure retail + OpenAI published rates). Not observed billing.

| Resource | SKU / config | Est. cost | Notes |
|----------|--------------|-----------|-------|
| PostgreSQL Flexible Server | Burstable **B1ms** (1 vCore, 2 GiB), 32 GiB storage | **£12–14** | Always-on; largest unavoidable fixed cost |
| Azure Cache for Redis | **Basic C0** (250 MB) | **£12–15** | Sessions / rate-limit counters; always-on |
| Azure Service Bus | **Basic** namespace | **£8** | Queue for Analysis Runs |
| Container Apps Environment | Consumption, shared | **£0–3** | Minimal when scaled to zero |
| Container Apps — API | 0.5 vCPU, 1 GiB; min **0** / max **2** | **£2–8** | Billed only when replicas active; cold-start on first request |
| Container Apps — Worker | 0.5 vCPU, 1 GiB; min **0** / max **2**; KEDA | **£3–10** | Active during scrape + scoring (~5–20 min/run) |
| Azure Blob Storage | LRS, &lt;5 GB CVs + TF artifacts | **£1** | Few PDFs at Profile A volume |
| Azure Key Vault | Standard, &lt;10k ops | **£1–2** | OAuth, email, OpenAI, Adzuna secrets |
| Azure Container Registry | **Basic** | **£4–5** | SHA-tagged `api` + `worker` images |
| Terraform remote state | LRS storage account | **£1** | Bootstrap stack |
| Egress / HTTPS | Minimal UI + API | **£1–2** | Low traffic |
| Transactional email | Provider free/low tier | **£0–2** | &lt;100 emails/month |
| **OpenAI — GPT-4o-mini** | Title suggestions | **£1–2** | ~1 call per CV upload |
| **OpenAI — GPT-4o** | Per-listing scoring | **£12–28** | 10–30 runs × 40–80 listings × ~£0.04–0.06/listing |
| **Subtotal — Azure fixed** | | **£45–52** | Dominated by Postgres + Redis + Service Bus |
| **Subtotal — Azure variable** | | **£6–20** | ACA compute when jobs run |
| **Subtotal — OpenAI** | | **£13–30** | Dominates variable spend |
| **Total** | | **£64–102** | **Target £55–72** at Profile A mid-range |

**Mid-range planning figure:** **~£68/month** (20 runs, ~60 listings/run, moderate ACA uptime).

Azure pricing reference: [Azure pricing calculator](https://azure.microsoft.com/en-gb/pricing/calculator/) — uksouth, Container Apps consumption, PostgreSQL Burstable B1ms, Redis Basic C0.

## 3. Cost-to-Serve

- **Cost per Analysis Run (mid):** ~**£2.50–3.50** (~£0.75–1.00 OpenAI + ~£0.50 ACA worker + ~£1.50 fixed amortised over 20 runs).
- **Cost per 1,000 API requests:** **N/A at demo volume** — &lt;2k requests/month expected; fixed store costs dominate.
- **Fixed vs variable split:** ~**70% fixed** (Postgres, Redis, Service Bus, ACR, KV), ~**30% variable** (OpenAI + ephemeral ACA compute).
- **Scale-to-zero break-even:** Accepted. Idle ACA savings (~£15–25/mo vs `minReplicas=1` API) outweigh cold-start UX cost for solo demo traffic. First request after idle may take **30–60 seconds** (API replica spin-up).

### OpenAI guardrail math

| Runs/mo | Listings/run | Est. GPT-4o cost | Within £75 cap? |
|---------|--------------|------------------|-----------------|
| 10 | 50 | ~£8–12 | Yes |
| 20 | 60 | ~£15–22 | Yes |
| 30 | 100 (max) | ~£28–38 | Yes, if Azure stays lean |
| 30 | 100 + abuse spike | ~£50+ OpenAI alone | **Risk** — rely on quota + spend alert |

Hard per-run ceiling from product: **100 scoring calls** × quota **3/day** × 1 user ≈ max **90 runs/month** theoretical — Profile A assumes self-restraint.

## 4. Optimization Policies

1. **Scaling bounds** — API and Worker: `minReplicas=0`, `maxReplicas=2`. Worker scales on Service Bus queue depth (KEDA). No custom autoscale rules beyond queue depth in v1.
2. **SKU floor** — Smallest viable prod SKUs: PostgreSQL Burstable B1ms, Redis Basic C0, Service Bus Basic, ACR Basic. Revisit only if connection limits or queue throughput block runs.
3. **Teardown** — If idle &gt; **30 days** with no planned demo, run `terraform destroy` on main stack (see README when available). Destroy order: application stack before bootstrap/state per IaC convention. CVs in Blob are deleted with stack unless exported.
4. **Tagging** — Required on all Azure resources: `project=ai-job-matcher`, `env=prod`, `owner=<operator-email>`, `cost-center=portfolio`. Enables Cost Management filtering and chargeback if subscription is shared.
5. **Alerts** — (a) Azure Cost Management budget **£75** with email at **80%** and **100%**; (b) OpenAI org daily spend alert at **£2/day** (~£60/mo run-rate); (c) Service Bus queue depth sustained &gt; **10** for 15 min (abuse or worker failure) per THREAT_MODEL.md.
6. **Image retention** — Keep last **5** SHA-tagged images per app in ACR; purge older tags quarterly to limit storage.
7. **Deferred optimizations** — Reserved capacity, spot/preemptible compute, Azure Front Door, paid staging environment, multi-region, GPT batch API.

## 5. Accepted Cost Risks

| Risk | Why accepted | Mitigation |
|------|--------------|------------|
| **Cold-start latency** (scale-to-zero API) | Minimise fixed Azure cost within £75 cap | UI loading state; operator warms URL before demos |
| **Always-on Postgres + Redis** | Cannot scale data plane to zero; needed for sessions and quotas | Smallest SKUs; teardown when project paused |
| **OpenAI spike from unlimited allowlist** | Friends/family may run more than operator | 1 concurrent run cap; daily spend alert; manual revoke via `/admin` |
| **No auto-teardown on budget breach** | Operator wants control, not surprise destroy | 80% alert triggers manual review; OpenAI key rotation if abuse |
| **Indeed scrape without paid proxy** | ADR-0001 accepted legal/ToS risk | Adzuna fallback; no added infra cost |
| **List-price estimate drift** | No Terraform deployed yet; SKUs not observed | Re-estimate after first full billing cycle |

## 6. Review Cadence

- **After first Azure invoice** — Compare actuals to §2; adjust SKU or scaling if &gt;£60.
- **On MVP public launch** — Revisit traffic profile and cold-start tolerance.
- **When adding staging, custom domain, or `minReplicas≥1`** — Full re-estimate required.
- **Quarterly** — Confirm tags, ACR retention, and OpenAI alert threshold still match usage.
