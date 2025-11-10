resource "tls_private_key" "vpn" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "vpn" {
  key_name   = var.ssh_key_pair_name
  public_key = tls_private_key.vpn.public_key_openssh

  tags = merge(local.tags, {
    Name = "${var.project_name}-key"
  })
}
