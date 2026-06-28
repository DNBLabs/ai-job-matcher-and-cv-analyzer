# Inputs for the application stack. Tag values default to the FinOps-mandated
# scheme (CONTEXT.md §Tagging): project / env / owner / cost-center.

variable "location" {
  description = "Azure region. UK-scoped product (docs/finance/BUDGET.md)."
  type        = string
  default     = "uksouth"
}

variable "project" {
  description = "Project tag value and base name."
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

# Compact token for globally-scoped resource names (storage, ACR, Key Vault,
# Service Bus, Postgres) that disallow dashes or have tight length limits.
variable "name_token" {
  description = "Short lowercase-alphanumeric token for globally-unique resource names."
  type        = string
  default     = "aijm"

  validation {
    condition     = can(regex("^[a-z0-9]{2,8}$", var.name_token))
    error_message = "name_token must be 2-8 lowercase alphanumeric characters."
  }
}

variable "email_from" {
  description = "Shared mailbox the Graph sendMail backend sends transactional email from (CONTEXT 2026-06-11)."
  type        = string
  default     = "noreply@dnblabs.co.uk"
}

variable "postgres_administrator_login" {
  description = "PostgreSQL administrator login name."
  type        = string
  default     = "jobmatcher_admin"
}

variable "postgres_version" {
  description = "PostgreSQL major version for the Flexible Server."
  type        = string
  default     = "16"
}

variable "vnet_address_space" {
  description = "Address space for the application VNet."
  type        = string
  default     = "10.20.0.0/16"
}

# Operator/CI public IPs allowed to reach Key Vault to set secret values
# out-of-band. Empty by default; Key Vault otherwise denies all but the ACA
# subnet (service endpoint) and trusted Azure services.
variable "operator_ip_rules" {
  description = "Public IP CIDRs allowed through the Key Vault network ACL for out-of-band secret management."
  type        = list(string)
  default     = []
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for dnblabs.co.uk. Required — passed via -var or CLOUDFLARE_ZONE_ID secret in CI."
  type        = string
}

variable "frontend_custom_domain" {
  description = "Custom domain for the SPA (SWA). Canonical frontend URL used in ALLOWED_ORIGINS and POST_AUTH_REDIRECT_URL."
  type        = string
  default     = "www.getmeajob.dnblabs.co.uk"
}

variable "api_custom_domain" {
  description = "Custom domain for the API Container App. Used for the ACA custom domain + managed cert only; api_public_url is NOT changed here."
  type        = string
  default     = "api.getmeajob.dnblabs.co.uk"
}
