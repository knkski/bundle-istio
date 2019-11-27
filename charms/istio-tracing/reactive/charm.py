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

    layer.caas_base.pod_spec_set(
        {
            "version": 2,
            "containers": [
                {
                    "name": "jaeger",
                    "imageDetails": {
                        "imagePath": image_info.registry_path,
                        "username": image_info.username,
                        "password": image_info.password,
                    },
                    "ports": [
                        {"name": "http", "containerPort": 9411},
                        {"name": "query-http", "containerPort": 16686},
                        {
                            "name": "agnt-zpkn-thrft",
                            "containerPort": 5775,
                            "protocol": "UDP",
                        },
                        {
                            "name": "agent-compact",
                            "containerPort": 6831,
                            "protocol": "UDP",
                        },
                        {
                            "name": "agent-binary",
                            "containerPort": 6832,
                            "protocol": "UDP",
                        },
                    ],
                    "config": {
                        "POD_NAMESPACE": os.environ["JUJU_MODEL_NAME"],
                        "COLLECTOR_ZIPKIN_HTTP_PORT": "9411",
                        "MEMORY_MAX_TRACES": "50000",
                        "QUERY_BASE_PATH": "/jaeger",
                    },
                }
            ],
        }
    )

    layer.status.maintenance("creating container")
    set_flag("charm.started")
