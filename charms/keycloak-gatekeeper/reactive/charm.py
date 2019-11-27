import os

from charms import layer
from charms.reactive import clear_flag, hook, set_flag, when, when_any, when_not


@hook("upgrade-charm")
def upgrade_charm():
    clear_flag("charm.started")


@when("charm.started")
def charm_ready():
    layer.status.active("")


@when_any("layer.docker-resource.oci-image.changed", "config.changed")
def update_image():
    clear_flag("charm.started")


@when("layer.docker-resource.oci-image.available")
@when_not("charm.started")
def start_charm():
    layer.status.maintenance("configuring container")

    image_info = layer.docker_resource.get_info("oci-image")

    namespace = os.environ["JUJU_MODEL_NAME"]

    layer.caas_base.pod_spec_set(
        {
            "version": 2,
            "containers": [
                {
                    "name": "keycloak-gatekeeper",
                    "imageDetails": {
                        "imagePath": image_info.registry_path,
                        "username": image_info.username,
                        "password": image_info.password,
                    },
                    "args": [
                        "--listen=:3000",
                        "--client-id=ldapdexapp",
                        "--client-secret=pUBnBOY80SnXgjibTYM9ZWNzY2xreNGQok",
                        "--secure-cookie=false",
                        "--discovery-url=http://dex.example.com:31200",
                        "--upstream-url=http://kubeflow.centraldashboard.com:31380",
                        "--redirection-url=http://keycloak-gatekeeper.example.com:31204",
                        "--scopes=groups",
                        "--sign-in-page=/opt/templates/sign_in.html.tmpl",
                        "--forbidden-page=/opt/templates/forbidden.html.tmpl",
                        "--enable-refresh-tokens=true",
                        "--http-only-cookie=true",
                        "--preserve-host=true",
                        "--enable-encrypted-token=true",
                        "--encryption-key=nm6xjpPXPJFInLYo",
                        "--enable-authorization-header",
                        "--resources=uri=/*",
                    ],
                    "config": {"POD_NAMESPACE": namespace},
                    "ports": [{"name": "http", "containerPort": 3000}],
                    "files": [
                        {
                            "name": "templates",
                            "mountPath": "/opt/templates",
                            "files": {
                                "forbidden.html.tmpl": "FORBIDDEN PAGE TODO PUT IN TEMPLATE",
                                "sign_in.html.tmpl": "SIGN IN PAGE TODO PUT IN TEMPLATE",
                            },
                        },
                    ]
                }
            ],
        }
    )

    layer.status.maintenance("creating container")
    set_flag("charm.started")
