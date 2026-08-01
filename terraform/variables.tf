variable "project_name" {
  description = "Base name for all resources"
  type        = string
  default     = "secure-coding-study"
}

variable "location" {
  description = "Azure region to deploy resources"
  type        = string
  default     = "UK South"
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default = {
    environment = "research"
    project     = "secure-coding-study"
    owner       = "seyi"
  }
}

variable "acr_sku" {
  description = "SKU for Azure Container Registry (Basic, Standard, Premium)"
  type        = string
  default     = "Basic"
}

variable "image_tag" {
  description = "Docker image tag to deploy"
  type        = string
  default     = "latest"
}

# Secrets — passed in at apply time, never hardcoded
variable "openai_api_key" {
  description = "OpenAI API key — passed as a secure environment variable into the container"
  type        = string
  sensitive   = true
}

variable "frontend_origin" {
  description = "Allowed CORS origin — the Vercel frontend URL (e.g. https://your-app.vercel.app)"
  type        = string
}

# Azure credentials
variable "subscription_id" {
  description = "Azure Subscription ID used by Terraform"
  type        = string
}

variable "tenant_id" {
  description = "Azure Tenant ID used by Terraform"
  type        = string
}

variable "langfuse_public_key" {
  description = "Langfuse public key for agent tracing (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "langfuse_secret_key" {
  description = "Langfuse secret key for agent tracing (optional)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "participant_register_key" {
  description = "Secret key Apps Script uses to register participants via POST /participants/register"
  type        = string
  sensitive   = true
}

variable "monitoring_api_key" {
  description = "API key for GET /participants/status monitoring endpoint (optional)"
  type        = string
  sensitive   = true
  default     = ""
}
