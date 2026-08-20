output "ecr_repository_url" {
  description = "ERC repo's URL to upload Docker images"
  value       = aws_ecr_repository.app_repo.repository_url
}

output "vpc_id" {
  description = "VPC ID used"
  value       = aws_default_vpc.default.id
}

output "security_group_id" {
  description = "Security Group ID created for the service"
  value       = aws_security_group.app_sg.id
}