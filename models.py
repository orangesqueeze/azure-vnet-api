import ipaddress
import re

AZURE_RESOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}[A-Za-z0-9_]$")


class ValidationError(Exception):
    pass


def _parse_cidr(cidr_text, field_description):
    try:
        return ipaddress.ip_network(cidr_text, strict=True)
    except (ValueError, TypeError) as error:
        raise ValidationError(f"{field_description} '{cidr_text}' is not a valid CIDR") from error


def validate_request(request_body) -> dict:
    """Validate payload:
    {"name": str, "location": str, "addressSpace": ["10.0.0.0/16"],
     "subnets": [{"name": str, "addressPrefix": "10.0.1.0/24"}]}
    """
    if not isinstance(request_body, dict):
        raise ValidationError("body must be a JSON object")

    vnet_name = request_body.get("name")
    if not isinstance(vnet_name, str) or not AZURE_RESOURCE_NAME_PATTERN.match(vnet_name):
        raise ValidationError("invalid 'name'")
    location = request_body.get("location") or None

    address_space_cidrs = request_body.get("addressSpace")
    if not isinstance(address_space_cidrs, list) or not address_space_cidrs:
        raise ValidationError("'addressSpace' must be a non-empty list of CIDRs")
    address_space_networks = [_parse_cidr(cidr, "addressSpace") for cidr in address_space_cidrs]

    subnets = request_body.get("subnets")
    if not isinstance(subnets, list) or not subnets:
        raise ValidationError("'subnets' must be a non-empty list")

    seen_subnet_names = set()
    accepted_subnet_networks = []
    for subnet in subnets:
        if not isinstance(subnet, dict) or not AZURE_RESOURCE_NAME_PATTERN.match(
            str(subnet.get("name", ""))
        ):
            raise ValidationError("each subnet needs a valid 'name'")
        subnet_name = subnet["name"]
        if subnet_name in seen_subnet_names:
            raise ValidationError(f"duplicate subnet name '{subnet_name}'")
        seen_subnet_names.add(subnet_name)

        subnet_network = _parse_cidr(
            subnet.get("addressPrefix"), f"subnet {subnet_name} addressPrefix"
        )
        is_inside_address_space = any(
            subnet_network.version == space.version and subnet_network.subnet_of(space)
            for space in address_space_networks
        )
        if not is_inside_address_space:
            raise ValidationError(f"subnet '{subnet_name}' is outside the address space")
        for other_network in accepted_subnet_networks:
            if subnet_network.overlaps(other_network):
                raise ValidationError(f"subnet '{subnet_name}' overlaps another subnet")
        accepted_subnet_networks.append(subnet_network)

    return {
        "name": vnet_name,
        "location": location,
        "addressSpace": address_space_cidrs,
        "subnets": [
            {"name": subnet["name"], "addressPrefix": subnet["addressPrefix"]} for subnet in subnets
        ],
    }
