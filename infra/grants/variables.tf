# Inputs mirror the app stack so the managed-identity and resource-group names
# resolve identically (infra/app/main.tf, infra/app/identity.tf).

variable "project" {
  description = "Project base name (matches infra/app var.project)."
  type        = string
  default     = "ai-job-matcher"
}

variable "environment" {
  description = "Environment tag value (matches infra/app var.environment)."
  type        = string
  default     = "prod"
}
