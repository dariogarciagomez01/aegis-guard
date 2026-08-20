resource "aws_cloudwatch_log_group" "app_logs" {
  name              = "/ecs/${var.project_name}"
  retention_in_days = 7 # Borra logs tras 7 días para evitar costes de almacenamiento
}