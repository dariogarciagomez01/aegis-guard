output "ecr_repository_url" {
  description = "ERC repo's URL to upload Docker images"
  value       = aws_ecr_repository.app_repo.repository_url
}