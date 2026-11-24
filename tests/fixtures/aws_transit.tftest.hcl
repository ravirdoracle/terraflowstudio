mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_odb_network" {
    defaults = {
      arn                  = "arn:aws:odb:us-east-1:123456789012:odb-network/odbnet-1234567890abcdef"
      availability_zone_id = "use1-az6"
      client_subnet_cidr   = "10.10.0.0/24"
      backup_subnet_cidr   = "10.10.1.0/24"
    }
  }
  mock_data "aws_vpc" {
    defaults = { owner_id = "123456789012" }
  }
  mock_data "aws_subnet" {
    defaults = { vpc_id = "vpc-0123456789abcdef0", availability_zone_id = "use1-az6" }
  }
  mock_data "aws_ec2_transit_gateway_vpc_attachment" {
    defaults = {
      vpc_id             = "vpc-0123456789abcdef0"
      transit_gateway_id = "tgw-0123456789abcdef0"
      subnet_ids         = ["subnet-0123456789abcdef0"]
    }
  }
  mock_data "aws_odb_network_peering_connection" {
    defaults = {
      odb_network_arn  = "arn:aws:odb:us-east-1:123456789012:odb-network/odbnet-1234567890abcdef"
      peer_network_arn = "arn:aws:ec2:us-east-1:123456789012:vpc/vpc-0123456789abcdef0"
    }
  }
}
variables {
  name           = "hub"
  region         = "us-east-1"
  odb_network_id = "odbnet-1234567890abcdef"
}

run "new_transit_single_az" {
  command = plan
  variables {
    config = {
      "network_ref" : "net",
      "region" : "",
      "vpc_mode" : "create",
      "vpc_cidr" : "10.90.0.0/16",
      "subnet_cidr" : "10.90.0.0/28",
      "vpc_id" : "",
      "subnet_id" : "",
      "transit_gateway_id" : "tgw-0123456789abcdef0",
      "transit_gateway_route_table_id" : "tgw-rtb-0123456789abcdef0",
      "attachment_mode" : "create",
      "attachment_id" : "",
      "peering_mode" : "create",
      "peering_id" : "",
      "odb_cidrs" : [
        "10.10.0.0/24",
        "10.10.1.0/24"
      ],
      "client_cidrs" : [
        "10.20.0.0/16"
      ],
      "application_route_table_ids" : ["rtb-0123456789abcdef0"],
      "manage_vpc_routes" : true,
      "manage_tgw_routes" : true,
      "register_peer_cidrs" : false
    }
  }
  assert {
    condition     = length(aws_subnet.attachment) == 1 && length(aws_ec2_transit_gateway_vpc_attachment.transit[0].subnet_ids) == 1
    error_message = "Transit attachment must use exactly one subnet."
  }
  assert {
    condition     = aws_subnet.attachment[0].availability_zone_id == "use1-az6"
    error_message = "New transit subnet must use the ODB network AZ ID."
  }
  assert {
    condition     = alltrue([for route in aws_route.transit_to_odb : route.odb_network_arn == "arn:aws:odb:us-east-1:123456789012:odb-network/odbnet-1234567890abcdef"])
    error_message = "Transit subnet routes must target the ODB network ARN."
  }
  assert {
    condition     = length(aws_route.application_to_odb) == 0
    error_message = "Application route activation must wait for phase 2 CIDR registration."
  }
}

run "reuse_connections_without_managed_routes" {
  command = plan
  variables {
    config = {
      "network_ref" : "net",
      "region" : "",
      "vpc_mode" : "existing",
      "vpc_cidr" : "10.90.0.0/16",
      "subnet_cidr" : "10.90.0.0/28",
      "vpc_id" : "vpc-0123456789abcdef0",
      "subnet_id" : "subnet-0123456789abcdef0",
      "transit_gateway_id" : "tgw-0123456789abcdef0",
      "transit_gateway_route_table_id" : "tgw-rtb-0123456789abcdef0",
      "attachment_mode" : "existing",
      "attachment_id" : "tgw-attach-0123456789abcdef0",
      "peering_mode" : "existing",
      "peering_id" : "odbpcx-1234567890abcdef",
      "odb_cidrs" : [
        "10.10.0.0/24",
        "10.10.1.0/24"
      ],
      "client_cidrs" : [
        "10.20.0.0/16"
      ],
      "application_route_table_ids" : [],
      "manage_vpc_routes" : false,
      "manage_tgw_routes" : false,
      "register_peer_cidrs" : false
    }
  }
  assert {
    condition     = length(aws_vpc.transit) == 0 && length(aws_subnet.attachment) == 0 && length(aws_ec2_transit_gateway_vpc_attachment.transit) == 0 && length(aws_odb_network_peering_connection.transit) == 0
    error_message = "Reusing existing resources must not plan replacement VPCs or connections."
  }
  assert {
    condition     = length(aws_route.transit_to_odb) == 0 && length(aws_ec2_transit_gateway_route.to_odb) == 0 && length(aws_ec2_transit_gateway_route_table_association.transit) == 0
    error_message = "Externally managed routing must not be modified."
  }
}

run "wrong_az_is_rejected" {
  command = plan
  variables {
    config = {
      "network_ref" : "net",
      "region" : "",
      "vpc_mode" : "existing",
      "vpc_cidr" : "10.90.0.0/16",
      "subnet_cidr" : "10.90.0.0/28",
      "vpc_id" : "vpc-0123456789abcdef0",
      "subnet_id" : "subnet-0123456789abcdef0",
      "transit_gateway_id" : "tgw-0123456789abcdef0",
      "transit_gateway_route_table_id" : "tgw-rtb-0123456789abcdef0",
      "attachment_mode" : "existing",
      "attachment_id" : "tgw-attach-0123456789abcdef0",
      "peering_mode" : "existing",
      "peering_id" : "odbpcx-1234567890abcdef",
      "odb_cidrs" : [
        "10.10.0.0/24",
        "10.10.1.0/24"
      ],
      "client_cidrs" : [
        "10.20.0.0/16"
      ],
      "application_route_table_ids" : [],
      "manage_vpc_routes" : false,
      "manage_tgw_routes" : false,
      "register_peer_cidrs" : false
    }
  }
  override_data {
    target = data.aws_subnet.existing[0]
    values = { vpc_id = "vpc-0123456789abcdef0", availability_zone_id = "use1-az1" }
  }
  expect_failures = [data.aws_subnet.existing[0]]
}

run "wrong_odb_cidrs_are_rejected" {
  command = plan
  variables {
    config = {
      "network_ref" : "net",
      "region" : "",
      "vpc_mode" : "existing",
      "vpc_cidr" : "10.90.0.0/16",
      "subnet_cidr" : "10.90.0.0/28",
      "vpc_id" : "vpc-0123456789abcdef0",
      "subnet_id" : "subnet-0123456789abcdef0",
      "transit_gateway_id" : "tgw-0123456789abcdef0",
      "transit_gateway_route_table_id" : "tgw-rtb-0123456789abcdef0",
      "attachment_mode" : "existing",
      "attachment_id" : "tgw-attach-0123456789abcdef0",
      "peering_mode" : "existing",
      "peering_id" : "odbpcx-1234567890abcdef",
      "odb_cidrs" : [
        "10.99.0.0/24"
      ],
      "client_cidrs" : [
        "10.20.0.0/16"
      ],
      "application_route_table_ids" : [],
      "manage_vpc_routes" : false,
      "manage_tgw_routes" : false,
      "register_peer_cidrs" : false
    }
  }
  expect_failures = [data.aws_odb_network.selected]
}

run "phase_two_activates_application_routes" {
  command = plan
  variables {
    config = {
      "network_ref" : "net",
      "region" : "",
      "vpc_mode" : "create",
      "vpc_cidr" : "10.90.0.0/16",
      "subnet_cidr" : "10.90.0.0/28",
      "vpc_id" : "",
      "subnet_id" : "",
      "transit_gateway_id" : "tgw-0123456789abcdef0",
      "transit_gateway_route_table_id" : "tgw-rtb-0123456789abcdef0",
      "attachment_mode" : "create",
      "attachment_id" : "",
      "peering_mode" : "create",
      "peering_id" : "",
      "odb_cidrs" : [
        "10.10.0.0/24",
        "10.10.1.0/24"
      ],
      "client_cidrs" : [
        "10.20.0.0/16"
      ],
      "application_route_table_ids" : [
        "rtb-0123456789abcdef0"
      ],
      "manage_vpc_routes" : true,
      "manage_tgw_routes" : true,
      "register_peer_cidrs" : true
    }
  }
  assert {
    condition     = length(aws_route.application_to_odb) == 2
    error_message = "Phase 2 must create the requested client/backup ODB routes in each application route table."
  }
}
