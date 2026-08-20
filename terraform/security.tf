resource "aws_security_group" "app_sg" {
  name        = "${var.project_name}-sg"
  description = "Reglas de trafico de entrada y salida para Aegis Guard"
  vpc_id      = aws_default_vpc.default.id

  ingress {
    description = "Public access to proxy HTTP (Aegis Guard)"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Total output to Internet for upstream LLM APIs y DNS"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-sg"
  }
}