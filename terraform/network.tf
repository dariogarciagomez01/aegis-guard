resource "aws_default_vpc" "default" {
  tags = {
    Name = "${var.project_name}-default-vpc"
  }
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [aws_default_vpc.default.id]
  }
}