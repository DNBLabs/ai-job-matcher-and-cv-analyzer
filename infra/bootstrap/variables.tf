# Inputs for the bootstrap stack. Tag values default to the FinOps-mandated
# scheme (CONTEXT.md §Tagging, docs/finance/BUDGET.md): project / env / owner / cost-center.

variable "location" {
  description = "Azure region. UK-scoped product (docs/finance/BUDGET.md)."
  type        = string
  default     = "uksouth"
}

variable "project" {
  description = "Project tag value."
  type        = string
  default     = "ai-job-matcher"
}

variable "environment" {
  description = "Environment tag value (env)."
  type        = string
  default     = "prod"
}

variable "cost_center" {
  description = "Cost-center tag value."
  type        = string
  default     = "portfolio"
}

variable "owner_email" {
  description = "Operator email for the owner tag and cost accountability. Required (no default)."
  type        = string

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.owner_email))
    error_message = "owner_email must be a valid email address."
  }
}

variable "resource_group_name" {
  description = "Resource group holding the remote-state storage account."
  type        = string
  default     = "rg-ai-job-matcher-tfstate"
}

variable "state_storage_account_prefix" {
  description = "Prefix for the state storage account name. A random suffix is appended for global uniqueness (3-24 lowercase alphanumeric total)."
  type        = string
  default     = "staijmstate"

  validation {
    condition     = can(regex("^[a-z0-9]{1,18}$", var.state_storage_account_prefix))
    error_message = "Prefix must be 1-18 lowercase alphanumeric characters (leaves room for the 6-char suffix)."
  }
}

variable "state_container_name" {
  description = "Blob container holding the application-stack state blob."
  type        = string
  default     = "tfstate"
}

# ---- GitHub Actions OIDC deploy identity (Task 29) --------------------------

variable "github_repository" {
  description = "GitHub repository in 'owner/name' form. Scopes the OIDC federated credential subject so only this repo can assume the deploy identity."
  type        = string
  default     = "DNBLabs/ai-job-matcher-and-cv-analyzer"

  validation {
    condition     = can(regex("^[^/\\s]+/[^/\\s]+$", var.github_repository))
    error_message = "github_repository must be in 'owner/name' form."
  }
}

variable "github_deploy_branch" {
  description = "Branch the deploy workflow runs on. The federated credential trusts only this branch (CONTEXT.md §Supply chain: prod deploy on main only)."
  type        = string
  default     = "main"
}
