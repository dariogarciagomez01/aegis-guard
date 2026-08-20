variable "aws_region" {
  description = "AWS region where the resources will be deployed"
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Base name for the project resources"
  type        = string
  default     = "aegis-guard"
}