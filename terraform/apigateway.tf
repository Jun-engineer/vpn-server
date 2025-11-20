resource "aws_api_gateway_rest_api" "vpn" {
  name        = "${var.project_name}-api"
  description = "REST API controlling the VPN instance"
  endpoint_configuration {
    types = ["REGIONAL"]
  }
  tags = local.tags
}

resource "aws_api_gateway_resource" "start" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  parent_id   = aws_api_gateway_rest_api.vpn.root_resource_id
  path_part   = "start"
}

resource "aws_api_gateway_resource" "stop" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  parent_id   = aws_api_gateway_rest_api.vpn.root_resource_id
  path_part   = "stop"
}

resource "aws_api_gateway_resource" "status" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  parent_id   = aws_api_gateway_rest_api.vpn.root_resource_id
  path_part   = "status"
}

resource "aws_api_gateway_resource" "register" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  parent_id   = aws_api_gateway_rest_api.vpn.root_resource_id
  path_part   = "register"
}

resource "aws_api_gateway_method" "start" {
  rest_api_id      = aws_api_gateway_rest_api.vpn.id
  resource_id      = aws_api_gateway_resource.start.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_method" "start_options" {
  rest_api_id      = aws_api_gateway_rest_api.vpn.id
  resource_id      = aws_api_gateway_resource.start.id
  http_method      = "OPTIONS"
  authorization    = "NONE"
  api_key_required = false
}

resource "aws_api_gateway_method" "stop" {
  rest_api_id      = aws_api_gateway_rest_api.vpn.id
  resource_id      = aws_api_gateway_resource.stop.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_method" "stop_options" {
  rest_api_id      = aws_api_gateway_rest_api.vpn.id
  resource_id      = aws_api_gateway_resource.stop.id
  http_method      = "OPTIONS"
  authorization    = "NONE"
  api_key_required = false
}

resource "aws_api_gateway_method" "status" {
  rest_api_id      = aws_api_gateway_rest_api.vpn.id
  resource_id      = aws_api_gateway_resource.status.id
  http_method      = "GET"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_method" "status_options" {
  rest_api_id      = aws_api_gateway_rest_api.vpn.id
  resource_id      = aws_api_gateway_resource.status.id
  http_method      = "OPTIONS"
  authorization    = "NONE"
  api_key_required = false
}

resource "aws_api_gateway_method" "register" {
  rest_api_id      = aws_api_gateway_rest_api.vpn.id
  resource_id      = aws_api_gateway_resource.register.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = true
}

resource "aws_api_gateway_method" "register_options" {
  rest_api_id      = aws_api_gateway_rest_api.vpn.id
  resource_id      = aws_api_gateway_resource.register.id
  http_method      = "OPTIONS"
  authorization    = "NONE"
  api_key_required = false
}

resource "aws_api_gateway_integration" "start" {
  rest_api_id             = aws_api_gateway_rest_api.vpn.id
  resource_id             = aws_api_gateway_resource.start.id
  http_method             = aws_api_gateway_method.start.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.start_instance.invoke_arn
}

resource "aws_api_gateway_integration" "start_options" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.start.id
  http_method = aws_api_gateway_method.start_options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_integration" "stop" {
  rest_api_id             = aws_api_gateway_rest_api.vpn.id
  resource_id             = aws_api_gateway_resource.stop.id
  http_method             = aws_api_gateway_method.stop.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.stop_instance.invoke_arn
}

resource "aws_api_gateway_integration" "stop_options" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.stop.id
  http_method = aws_api_gateway_method.stop_options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_integration" "status" {
  rest_api_id             = aws_api_gateway_rest_api.vpn.id
  resource_id             = aws_api_gateway_resource.status.id
  http_method             = aws_api_gateway_method.status.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.check_status.invoke_arn
}

resource "aws_api_gateway_integration" "status_options" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.status.id
  http_method = aws_api_gateway_method.status_options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_integration" "register" {
  rest_api_id             = aws_api_gateway_rest_api.vpn.id
  resource_id             = aws_api_gateway_resource.register.id
  http_method             = aws_api_gateway_method.register.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.register_peer.invoke_arn
}

resource "aws_api_gateway_integration" "register_options" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.register.id
  http_method = aws_api_gateway_method.register_options.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "start_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.start.id
  http_method = aws_api_gateway_method.start.http_method
  status_code = "200"
}

resource "aws_api_gateway_method_response" "start_options_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.start.id
  http_method = aws_api_gateway_method.start_options.http_method
  status_code = "200"

  response_models = {
    "application/json" = "Empty"
  }

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true,
    "method.response.header.Access-Control-Allow-Methods" = true,
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_method_response" "stop_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.stop.id
  http_method = aws_api_gateway_method.stop.http_method
  status_code = "200"
}

resource "aws_api_gateway_method_response" "stop_options_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.stop.id
  http_method = aws_api_gateway_method.stop_options.http_method
  status_code = "200"

  response_models = {
    "application/json" = "Empty"
  }

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true,
    "method.response.header.Access-Control-Allow-Methods" = true,
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_method_response" "status_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.status.id
  http_method = aws_api_gateway_method.status.http_method
  status_code = "200"
}

resource "aws_api_gateway_method_response" "status_options_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.status.id
  http_method = aws_api_gateway_method.status_options.http_method
  status_code = "200"

  response_models = {
    "application/json" = "Empty"
  }

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true,
    "method.response.header.Access-Control-Allow-Methods" = true,
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_method_response" "register_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.register.id
  http_method = aws_api_gateway_method.register.http_method
  status_code = "200"
}

resource "aws_api_gateway_method_response" "register_options_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.register.id
  http_method = aws_api_gateway_method.register_options.http_method
  status_code = "200"

  response_models = {
    "application/json" = "Empty"
  }

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true,
    "method.response.header.Access-Control-Allow-Methods" = true,
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

locals {
  api_cors_allow_headers = "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token"
}

resource "aws_api_gateway_integration_response" "start_options_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.start.id
  http_method = aws_api_gateway_method.start_options.http_method
  status_code = aws_api_gateway_method_response.start_options_200.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'${local.api_cors_allow_headers}'",
    "method.response.header.Access-Control-Allow-Methods" = "'OPTIONS,POST'",
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

resource "aws_api_gateway_integration_response" "stop_options_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.stop.id
  http_method = aws_api_gateway_method.stop_options.http_method
  status_code = aws_api_gateway_method_response.stop_options_200.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'${local.api_cors_allow_headers}'",
    "method.response.header.Access-Control-Allow-Methods" = "'OPTIONS,POST'",
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

resource "aws_api_gateway_integration_response" "status_options_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.status.id
  http_method = aws_api_gateway_method.status_options.http_method
  status_code = aws_api_gateway_method_response.status_options_200.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'${local.api_cors_allow_headers}'",
    "method.response.header.Access-Control-Allow-Methods" = "'OPTIONS,GET'",
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

resource "aws_api_gateway_integration_response" "register_options_200" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  resource_id = aws_api_gateway_resource.register.id
  http_method = aws_api_gateway_method.register_options.http_method
  status_code = aws_api_gateway_method_response.register_options_200.status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'${local.api_cors_allow_headers}'",
    "method.response.header.Access-Control-Allow-Methods" = "'OPTIONS,POST'",
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
}

resource "aws_api_gateway_deployment" "vpn" {
  rest_api_id = aws_api_gateway_rest_api.vpn.id
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_integration.start.id,
      aws_api_gateway_integration.stop.id,
      aws_api_gateway_integration.status.id,
      aws_api_gateway_integration.register.id,
      aws_api_gateway_integration.start_options.id,
      aws_api_gateway_integration.stop_options.id,
      aws_api_gateway_integration.status_options.id,
      aws_api_gateway_integration.register_options.id,
      aws_api_gateway_integration_response.start_options_200.id,
      aws_api_gateway_integration_response.stop_options_200.id,
      aws_api_gateway_integration_response.status_options_200.id,
      aws_api_gateway_integration_response.register_options_200.id
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_method_response.start_200,
    aws_api_gateway_method_response.stop_200,
    aws_api_gateway_method_response.status_200,
    aws_api_gateway_method_response.register_200,
    aws_api_gateway_method_response.start_options_200,
    aws_api_gateway_method_response.stop_options_200,
    aws_api_gateway_method_response.status_options_200,
    aws_api_gateway_method_response.register_options_200,
    aws_api_gateway_integration_response.start_options_200,
    aws_api_gateway_integration_response.stop_options_200,
    aws_api_gateway_integration_response.status_options_200,
    aws_api_gateway_integration_response.register_options_200
  ]
}

resource "aws_api_gateway_stage" "prod" {
  rest_api_id   = aws_api_gateway_rest_api.vpn.id
  deployment_id = aws_api_gateway_deployment.vpn.id
  stage_name    = "prod"
  tags          = local.tags
}

resource "aws_api_gateway_gateway_response" "default_4xx" {
  rest_api_id   = aws_api_gateway_rest_api.vpn.id
  response_type = "DEFAULT_4XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'",
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'${local.api_cors_allow_headers}'",
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'OPTIONS,GET,POST'"
  }
}

resource "aws_api_gateway_gateway_response" "default_5xx" {
  rest_api_id   = aws_api_gateway_rest_api.vpn.id
  response_type = "DEFAULT_5XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'",
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'${local.api_cors_allow_headers}'",
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'OPTIONS,GET,POST'"
  }
}

resource "aws_api_gateway_api_key" "vpn" {
  name = var.api_key_name
  tags = local.tags
}

resource "aws_api_gateway_usage_plan" "vpn" {
  name = var.api_usage_plan_name

  api_stages {
    api_id = aws_api_gateway_rest_api.vpn.id
    stage  = aws_api_gateway_stage.prod.stage_name
  }

  throttle_settings {
    burst_limit = var.allowed_api_burst
    rate_limit  = var.allowed_api_rate
  }

  quota_settings {
    limit  = var.allowed_api_quota
    offset = 0
    period = "MONTH"
  }

  tags = local.tags
}

resource "aws_api_gateway_usage_plan_key" "vpn" {
  key_id        = aws_api_gateway_api_key.vpn.id
  key_type      = "API_KEY"
  usage_plan_id = aws_api_gateway_usage_plan.vpn.id
}

resource "aws_lambda_permission" "apigw_start" {
  statement_id  = "AllowAPIGatewayInvokeStart"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.start_instance.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.vpn.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_stop" {
  statement_id  = "AllowAPIGatewayInvokeStop"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.stop_instance.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.vpn.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_status" {
  statement_id  = "AllowAPIGatewayInvokeStatus"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.check_status.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.vpn.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_register" {
  statement_id  = "AllowAPIGatewayInvokeRegister"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.register_peer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.vpn.execution_arn}/*/*"
}
