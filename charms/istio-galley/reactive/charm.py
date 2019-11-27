import os
from pathlib import Path
from subprocess import run

import yaml

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

    namespace = os.environ["JUJU_MODEL_NAME"]

    crds = yaml.safe_load_all(Path("files/crd.yaml").read_text())

    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:4096",
            "-keyout",
            "key.pem",
            "-out",
            "cert.pem",
            "-days",
            "365",
            "-subj",
            "/CN=localhost",
            "-nodes",
        ],
        check=True,
    )

    layer.caas_base.pod_spec_set(
        {
            "version": 2,
            "containers": [
                {
                    "name": "galley",
                    "command": [
                        "/usr/local/bin/galley",
                        "server",
                        "--meshConfigFile=/etc/mesh-config/mesh",
                        "--livenessProbeInterval=1s",
                        "--livenessProbePath=/healthliveness",
                        "--readinessProbePath=/healthready",
                        "--readinessProbeInterval=1s",
                        f"--deployment-namespace={namespace}",
                        "--insecure=true",
                        "--validation-webhook-config-file",
                        "/etc/config/validatingwebhookconfiguration.yaml",
                        "--monitoringPort=15014",
                        "--log_output_level=default:info",
                    ],
                    "imageDetails": {
                        "imagePath": image_info.registry_path,
                        "username": image_info.username,
                        "password": image_info.password,
                    },
                    "ports": [
                        {"name": "validation", "containerPort": 443},
                        {"name": "monitoring", "containerPort": 15014},
                        {"name": "grpc-mcp", "containerPort": 9901},
                    ],
                    "files": [
                        {
                            "name": "mesh-config",
                            "mountPath": "/etc/mesh-config",
                            "files": {
                                "mesh": Path("files/mesh.yaml").read_text(),
                                "meshNetworks": "networks: {}",
                            },
                        },
                        {
                            "name": "config",
                            "mountPath": "/etc/config",
                            "files": {
                                "validatingwebhookconfiguration.yaml": Path(
                                    "files/validatingwebhookconfiguration.yaml"
                                ).read_text()
                            },
                        },
                        {
                            "name": "certs",
                            "mountPath": "/etc/certs",
                            "files": {
                                "cert-chain.pem": Path("cert.pem").read_text(),
                                "key.pem": Path("key.pem").read_text(),
                            },
                        },
                    ],
                }
            ],
        },
        {
            'kubernetesResources': {
                'customResourceDefinitions': {crd["metadata"]["name"]: crd["spec"] for crd in crds},
            }
        }
    )

    layer.status.maintenance("creating container")
    set_flag("charm.started")
