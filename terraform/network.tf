resource "aws_vpc" "vpn" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(local.tags, {
    Name = "${var.project_name}-vpc"
  })
}

resource "aws_internet_gateway" "vpn" {
  vpc_id = aws_vpc.vpn.id

  tags = merge(local.tags, {
    Name = "${var.project_name}-igw"
  })
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.vpn.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.public_subnet_az
  map_public_ip_on_launch = false

  tags = merge(local.tags, {
    Name = "${var.project_name}-public-subnet"
  })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.vpn.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.vpn.id
  }

  tags = merge(local.tags, {
    Name = "${var.project_name}-public-rt"
  })
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

resource "aws_security_group" "vpn" {
  name        = "${var.project_name}-sg"
  description = "Security group for WireGuard VPN instance"
  vpc_id      = aws_vpc.vpn.id

  ingress {
    description = "WireGuard"
    from_port   = 51820
    to_port     = 51820
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, {
    Name = "${var.project_name}-sg"
  })
}

resource "aws_network_interface" "vpn" {
  subnet_id       = aws_subnet.public.id
  private_ip      = local.vpn_private_ip
  security_groups = [aws_security_group.vpn.id]

  tags = merge(local.tags, {
    Name = "${var.project_name}-eni"
  })
}

resource "aws_eip" "vpn" {
  domain            = "vpc"
  network_interface = aws_network_interface.vpn.id
  depends_on        = [aws_internet_gateway.vpn, aws_instance.vpn]

  tags = merge(local.tags, {
    Name = "${var.project_name}-eip"
  })
}

resource "aws_instance" "vpn" {
  ami               = var.vpn_ami_id
  instance_type     = var.vpn_instance_type
  availability_zone = var.public_subnet_az
  key_name          = aws_key_pair.vpn.key_name
  iam_instance_profile = aws_iam_instance_profile.instance.name

  network_interface {
    device_index         = 0
    network_interface_id = aws_network_interface.vpn.id
  }

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  tags = merge(local.tags, {
    Name = "${var.project_name}-ec2"
  })
}
