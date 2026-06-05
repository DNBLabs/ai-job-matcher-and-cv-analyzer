# ADR-0002: Azure Production with Cloud-Agnostic Application Ports

## Status

Accepted

## Context

The system requires:

- A **FastAPI** HTTP API and separate **background worker** processes.
- **Async job queue** driving worker scale based on queue depth (portfolio: auto-scaling compute).
- **PostgreSQL** for accounts, runs, scores, and FinOps metadata.
- **Encrypted object storage** for CV PDFs (PII).
- **Least-privilege access** to secrets and PII from workers (portfolio: DevSecOps / IAM).
- **Local development** without an Azure subscription.

We evaluated deployment targets:

| Option | Platform | Trade-off |
|---|---|---|
| A | **AWS ECS Fargate** + SQS + RDS + S3 | Mature story; operator preference is Azure |
| B | **Azure Container Apps** + Service Bus + PostgreSQL + Blob | Serverless containers, KEDA queue scaling, Managed Identity |
| C | **Kubernetes (AKS/EKS)** | Maximum flexibility; heavy ops for MVP |
| D | **Single VPS / Docker Compose only** | Fast start; no credible auto-scaling demo |

The operator chose **Azure** as the production target. Azure Container Apps is the closest equivalent to AWS ECS Fargate: serverless containers with scale rules driven by queue depth (via KEDA).

A separate question: should application code call Azure SDKs directly, or abstract cloud primitives behind internal interfaces?

## Decision

**Production deploys to Azure.** Application code remains **cloud-agnostic** via narrow internal ports and swappable adapters.

### Azure production stack

| Concern | Azure service |
|---|---|
| API + workers | Azure Container Apps (separate apps/services) |
| Job queue | Azure Service Bus |
| Database | Azure Database for PostgreSQL Flexible Server |
| CV storage | Azure Blob Storage (encryption at rest) |
| Cache / rate limits | Azure Cache for Redis |
| Secrets | Azure Key Vault |
| Identity | Managed Identity (least-privilege access to Blob, Key Vault, Service Bus) |
| IaC | Terraform (Azure-specific) |

Workers scale on Service Bus queue depth. API and workers run as standard Docker images.

### Cloud-agnostic application ports

Domain and worker code **must not** import Azure SDKs. Infrastructure bindings live in adapter modules:

| Port | Azure adapter (prod) | Local dev adapter |
|---|---|---|
| `BlobStore` | Blob Storage | Azurite or MinIO |
| `JobQueue` | Service Bus | RabbitMQ or in-process queue |
| `SecretProvider` | Key Vault | `.env` / Docker secrets |
| Database | PostgreSQL via connection string | PostgreSQL (Docker Compose) |

Terraform provisions Azure resources; adapters are wired at application startup from environment configuration.

## Consequences

### Positive

- Azure Container Apps + Service Bus + Managed Identity delivers the full portfolio narrative (async compute, auto-scaling, IAM for PII, encryption at rest).
- Port/adapter pattern allows local dev with Docker Compose and future migration to AWS (S3/SQS) or other clouds without rewriting domain logic.
- Standard Docker images are portable across ACA, local, and CI.

### Negative

- Adapter layer adds initial boilerplate (interfaces, two implementations per port for local + Azure).
- Some Azure features (Managed Identity, Service Bus sessions) are awkward to replicate locally; local adapters will behave slightly differently from prod.
- Terraform and ACA knowledge required for deployment; not "push to Render" simple.
- Operator must maintain both IaC (Azure) and adapter code; drift between adapters is a testing burden.

### Follow-ups

- Integration tests run against local adapters (Docker Compose); smoke tests run against Azure staging before prod.
- Document adapter wiring in README; single `docker compose up` must boot API + worker + Postgres + queue + blob emulator.
