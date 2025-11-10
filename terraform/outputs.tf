output "vpn_instance_id" {
  description = "ID of the managed VPN EC2 instance."
  value       = aws_instance.vpn.id
}

output "vpn_instance_public_ip" {
  description = "Elastic IP address assigned to the VPN ENI."
  value       = aws_eip.vpn.public_ip
}

output "vpn_private_ip" {
  description = "Private IP address assigned to the VPN ENI."
  value       = aws_network_interface.vpn.private_ip
}

output "api_invoke_url" {
  description = "Invoke URL for the API Gateway stage."
  value       = aws_api_gateway_stage.prod.invoke_url
}

output "api_key_id" {
  description = "Identifier of the generated API key. Retrieve the value from the AWS Console after apply."
  value       = aws_api_gateway_api_key.vpn.id
}

output "web_ui_bucket" {
  description = "Name of the S3 bucket hosting the Web UI."
  value       = aws_s3_bucket.web_ui.bucket
}

output "cloudfront_domain_name" {
  description = "CloudFront domain serving the Web UI."
  value       = aws_cloudfront_distribution.web_ui.domain_name
}

output "ssh_key_pair_name" {
  description = "Name of the generated EC2 key pair for SSH access."
  value       = aws_key_pair.vpn.key_name
}

output "ssh_private_key_pem" {
  description = "Private key (PEM format) for the generated EC2 key pair. Store securely."
  value       = tls_private_key.vpn.private_key_pem
  sensitive   = true
}
