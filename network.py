import os

from azure.identity import DefaultAzureCredential
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network.models import AddressSpace, Subnet, VirtualNetwork


def create_vnet(vnet_spec: dict) -> dict:
    """Create the VNet + subnets in the target resource group and return the stored record."""
    subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"]
    resource_group = os.environ["TARGET_RESOURCE_GROUP"]
    location = vnet_spec["location"] or os.environ.get("DEFAULT_LOCATION", "westus2")

    # Typed models, not dicts: the SDK sends dicts to Azure unconverted.
    requested_vnet = VirtualNetwork(
        location=location,
        address_space=AddressSpace(address_prefixes=vnet_spec["addressSpace"]),
        subnets=[
            Subnet(name=subnet["name"], address_prefix=subnet["addressPrefix"])
            for subnet in vnet_spec["subnets"]
        ],
    )

    network_client = NetworkManagementClient(DefaultAzureCredential(), subscription_id)
    created_vnet = network_client.virtual_networks.begin_create_or_update(
        resource_group, vnet_spec["name"], requested_vnet
    ).result()

    return {
        "name": created_vnet.name,
        "resourceId": created_vnet.id,
        "resourceGroup": resource_group,
        "location": created_vnet.location,
        "addressSpace": list(created_vnet.address_space.address_prefixes),
        "subnets": [
            {"name": subnet.name, "addressPrefix": subnet.address_prefix, "resourceId": subnet.id}
            for subnet in created_vnet.subnets
        ],
        "provisioningState": str(created_vnet.provisioning_state),
    }
