import os

from charms import layer
from charms.reactive import clear_flag, hook, set_flag, when, when_any, when_not


@hook("upgrade-charm")
def upgrade_charm():
    clear_flag("charm.started")


@when("charm.started")
def charm_ready():
    layer.status.active("")


@when_any("layer.docker-resource.oci-image.changed")
def update_image():
    clear_flag("charm.started")


@when("layer.docker-resource.oci-image.available")
@when_not("charm.started")
def start_charm():
    layer.status.maintenance("configuring container")

    image_info = layer.docker_resource.get_info("oci-image")

    model = os.environ["JUJU_MODEL_NAME"]

    layer.caas_base.pod_spec_set(
        {
            "version": 2,
            "serviceAccount": {
                "global": True,
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["configmaps"],
                        "verbs": ["create", "get", "update"],
                    },
                    {
                        "apiGroups": [""],
                        "resources": ["secrets"],
                        "verbs": ["create", "get", "watch", "list", "update", "delete"],
                    },
                    {
                        "apiGroups": [""],
                        "resources": ["serviceaccounts", "services"],
                        "verbs": ["get", "watch", "list"],
                    },
                    {
                        "apiGroups": ["authentication.k8s.io"],
                        "resources": ["tokenreviews"],
                        "verbs": ["create"],
                    },
                ],
            },
            "containers": [
                {
                    "name": "citadel",
                    "args": [
                        "--sds-enabled=false",
                        "--append-dns-names=true",
                        "--grpc-port=8060",
                        f"--citadel-storage-namespace={model}",
                        f"--custom-dns-names=istio-pilot-service-account.{model}:istio-pilot.{model}",
                        "--monitoring-port=15014",
                        "--self-signed-ca=true",
                        "--workload-cert-ttl=2160h",
                    ],
                    "imageDetails": {
                        "imagePath": image_info.registry_path,
                        "username": image_info.username,
                        "password": image_info.password,
                    },
                    "config": {"CITADEL_ENABLE_NAMESPACES_BY_DEFAULT": True},
                }
            ],
        }
    )

    layer.status.maintenance("creating container")
    set_flag("charm.started")
