from glob import glob
from pathlib import Path

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

    layer.caas_base.pod_spec_set(
        {
            "version": 2,
            "containers": [
                {
                    "name": "grafana",
                    "imageDetails": {
                        "imagePath": image_info.registry_path,
                        "username": image_info.username,
                        "password": image_info.password,
                    },
                    "config": {
                        "GRAFANA_PORT": "3000",
                        "GF_AUTH_BASIC_ENABLED": "false",
                        "GF_AUTH_ANONYMOUS_ENABLED": "true",
                        "GF_AUTH_ANONYMOUS_ORG_ROLE": "Admin",
                        "GF_PATHS_DATA": "/tmp/grafana",
                    },
                    "ports": [{"name": "http", "containerPort": 3000}],
                    "files": [
                        {
                            "name": "dashboards",
                            "mountPath": "/var/lib/grafana/dashboards/istio/",
                            "files": {
                                Path(filename)
                                .name: Path(filename)
                                .read_text(encoding="utf-8")
                                for filename in glob("files/*.json")
                            },
                        },
                        {
                            "name": "datasources",
                            "mountPath": "/etc/grafana/provisioning/datasources/",
                            "files": {
                                "datasources.yaml": Path(
                                    "files/datasources.yaml"
                                ).read_text()
                            },
                        },
                        {
                            "name": "providers",
                            "mountPath": "/etc/grafana/provisioning/dashboards/",
                            "files": {
                                "dashboardproviders.yaml": Path(
                                    "files/dashboardproviders.yaml"
                                ).read_text()
                            },
                        },
                    ],
                }
            ]
        }
    )

    layer.status.maintenance("creating container")
    set_flag("charm.started")
