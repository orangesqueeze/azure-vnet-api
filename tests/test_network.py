"""create_vnet builds a typed request for Azure (a plain snake_case dict is rejected by ARM)."""

from types import SimpleNamespace

from azure.mgmt.network.models import VirtualNetwork

import network

VNET_SPEC = {
    "name": "demo-vnet",
    "location": "westus2",
    "addressSpace": ["10.0.0.0/16"],
    "subnets": [
        {"name": "web", "addressPrefix": "10.0.1.0/24"},
        {"name": "db", "addressPrefix": "10.0.2.0/24"},
    ],
}


class FakeNetworkClient:
    """Records the create call and returns a canned ARM response."""

    def __init__(self, *args, **kwargs):
        self.sent = {}
        self.virtual_networks = self

    def begin_create_or_update(self, resource_group, vnet_name, vnet_body):
        self.sent = {"resource_group": resource_group, "name": vnet_name, "body": vnet_body}
        subnets = [
            SimpleNamespace(name=s.name, address_prefix=s.address_prefix, id=f"/subnets/{s.name}")
            for s in vnet_body.subnets
        ]
        created = SimpleNamespace(
            name=vnet_name,
            id=f"/vnets/{vnet_name}",
            location=vnet_body.location,
            address_space=vnet_body.address_space,
            subnets=subnets,
            provisioning_state="Succeeded",
        )
        return SimpleNamespace(result=lambda: created)


def test_create_vnet_sends_typed_model_with_arm_shape(monkeypatch):
    fake_client = FakeNetworkClient()
    monkeypatch.setenv("AZURE_SUBSCRIPTION_ID", "sub-id")
    monkeypatch.setenv("TARGET_RESOURCE_GROUP", "rg-test")
    monkeypatch.setattr(network, "DefaultAzureCredential", lambda: object())
    monkeypatch.setattr(network, "NetworkManagementClient", lambda *args: fake_client)

    record = network.create_vnet(VNET_SPEC)

    sent_body = fake_client.sent["body"]
    assert isinstance(sent_body, VirtualNetwork)
    assert sent_body.as_dict()["properties"]["addressSpace"]["addressPrefixes"] == ["10.0.0.0/16"]
    assert [
        s["properties"]["addressPrefix"] for s in sent_body.as_dict()["properties"]["subnets"]
    ] == [
        "10.0.1.0/24",
        "10.0.2.0/24",
    ]
    assert fake_client.sent["resource_group"] == "rg-test"
    assert record["resourceGroup"] == "rg-test"
    assert [s["name"] for s in record["subnets"]] == ["web", "db"]
