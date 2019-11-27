import os
from pathlib import Path
from subprocess import run

from charms import layer
from charms.reactive import (
    clear_flag,
    hook,
    hookenv,
    set_flag,
    when,
    when_any,
    when_not,
)


@hook("upgrade-charm")
def upgrade_charm():
    clear_flag("charm.started")


@when("charm.started")
def charm_ready():
    layer.status.active("")


@when_any(
    "layer.docker-resource.mixer-image.changed",
    "layer.docker-resource.proxy-image.changed",
)
def update_image():
    clear_flag("charm.started")


@when(
    "layer.docker-resource.mixer-image.available",
    "layer.docker-resource.proxy-image.available",
)
@when_not("charm.started")
def start_charm():
    layer.status.maintenance("configuring container")

    mixer_image = layer.docker_resource.get_info("mixer-image")
    proxy_image = layer.docker_resource.get_info("proxy-image")

    namespace = os.environ["JUJU_MODEL_NAME"]

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
                    "name": "mixer",
                    "args": [
                        "--monitoringPort=15014",
                        "--address",
                        "unix:///sock/mixer.socket",
                        "--log_output_level=default:info",
                        f"--configStoreURL=mcp://istio-galley.{namespace}.svc:9901",
                        f"--configDefaultNamespace={namespace}",
                        "--useAdapterCRDs=false",
                        "--useTemplateCRDs=false",
                        "--trace_zipkin_url=http://zipkin:9411/api/v1/spans",
                    ],
                    "imageDetails": {
                        "imagePath": mixer_image.registry_path,
                        "username": mixer_image.username,
                        "password": mixer_image.password,
                    },
                    "config": {"GODEBUG": "gctrace=1", "GOMAXPROCS": "6"},
                    "ports": [
                        {"name": "monitoring", "containerPort": 15014},
                        {"name": "prometheus", "containerPort": 42422},
                    ],
                    "files": [
                        {
                            "name": "istio-certs1",
                            "mountPath": "/etc/certs",
                            "files": {
                                "cert-chain.pem": Path("cert.pem").read_text(),
                                "key.pem": Path("key.pem").read_text(),
                            },
                        }
                    ],
                },
                {
                    "name": "proxy",
                    "args": [
                        "proxy",
                        "--domain",
                        f"{namespace}.svc.cluster.local",
                        "--serviceCluster",
                        hookenv.service_name(),
                        "--templateFile",
                        "/etc/istio/proxy/envoy_policy.yaml.tmpl",
                        "--controlPlaneAuthPolicy",
                        "NONE",
                    ],
                    "config": {
                        "POD_NAME": "metadata.name",
                        "POD_NAMESPACE": "metadata.namespace",
                        "INSTANCE_IP": "status.podIP",
                        "SDS_ENABLED": True,
                    },
                    "imageDetails": {
                        "imagePath": proxy_image.registry_path,
                        "username": proxy_image.username,
                        "password": proxy_image.password,
                    },
                    "ports": [
                        {"name": "grpc-mixer", "containerPort": 9091},
                        {"name": "grpc-mixer-mtls", "containerPort": 15004},
                        {
                            "name": "envoy-prom",
                            "containerPort": 15090,
                            "protocol": "TCP",
                        },
                    ],
                    "files": [
                        {
                            "name": "istio-certs2",
                            "mountPath": "/etc/certs",
                            "files": {
                                "cert-chain.pem": Path("cert.pem").read_text(),
                                "root-cert.pem": Path("cert.pem").read_text(),
                                "key.pem": Path("key.pem").read_text(),
                            },
                        },
                        {
                            "name": "policy-adapter-secret",
                            "mountPath": "/var/run/secrets/istio.io/policy/adapter",
                            "files": {"foo": "bar"},
                        },
                    ],
                },
            ],
        }
    )

    layer.status.maintenance("creating container")
    set_flag("charm.started")
