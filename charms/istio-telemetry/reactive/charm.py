import os
from pathlib import Path
from subprocess import run

from charms import layer
from charms.reactive import clear_flag, hook, set_flag, when, when_any, when_not


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

    model = os.environ["JUJU_MODEL_NAME"]

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
                        f"--configStoreURL=mcp://istio-galley.{model}.svc:9901",
                        "--certFile=/etc/certs/cert-chain.pem",
                        "--keyFile=/etc/certs/key.pem",
                        "--caCertFile=/etc/certs/root-cert.pem",
                        f"--configDefaultNamespace={model}",
                        "--useAdapterCRDs=false",
                        "--trace_zipkin_url=http://zipkin:9411/api/v1/spans",
                        "--averageLatencyThreshold",
                        "100ms",
                        "--loadsheddingMode",
                        "enforce",
                    ],
                    "imageDetails": {
                        "imagePath": mixer_image.registry_path,
                        "username": mixer_image.username,
                        "password": mixer_image.password,
                    },
                    "config": {"GODEBUG": "gctrace=1", "GOMAXPROCS": "6"},
                    "ports": [
                        {"name": "port-1", "containerPort": 15014},
                        {"name": "port-2", "containerPort": 42422},
                    ],
                    "files": [
                        {
                            "name": "istio-certs",
                            "mountPath": "/etc/certs",
                            "files": {
                                "cert-chain.pem": Path("cert.pem").read_text(),
                                "key.pem": Path("key.pem").read_text(),
                            },
                        },
                        #  {
                        #      "name": "telemetry-adapter-secret",
                        #      "mountPath": "/var/run/secrets/istio.io/telemetry/adapter",
                        #      "files": {},
                        #  },
                    ],
                },
                {
                    "name": "proxy",
                    "args": [
                        "proxy",
                        "--domain",
                        f"{model}.svc.cluster.local",
                        "--serviceCluster",
                        "istio-telemetry",
                        "--templateFile",
                        "/etc/istio/proxy/envoy_telemetry.yaml.tmpl",
                        "--controlPlaneAuthPolicy",
                        "NONE",
                    ],
                    "imageDetails": {
                        "imagePath": proxy_image.registry_path,
                        "username": proxy_image.username,
                        "password": proxy_image.password,
                    },
                    "config": {
                        "POD_NAME": {"field": {"path": "metadata.name", "api-version": "v1"}},
                        "POD_NAMESPACE": model,
                        "INSTANCE_IP": {
                            "field": {"path": "status.PodIP", "api-version": "v1"}
                        },
                        "SDS_ENABLED": False,
                    },
                    "ports": [
                        {"name": "port-3", "containerPort": 9091},
                        {"name": "port-4", "containerPort": 15004},
                        #  {
                        #      "name": "http-envoy-prom",
                        #      "containerPort": 15090,
                        #      "protocol": "TCP",
                        #  },
                    ],
                    "files": [
                        {
                            "name": "istio-certs2",
                            "mountPath": "/etc/certs",
                            "files": {
                                "cert-chain.pem": Path("cert.pem").read_text(),
                                "key.pem": Path("key.pem").read_text(),
                            },
                        }
                    ],
                },
            ],
        }
    )

    layer.status.maintenance("creating container")
    set_flag("charm.started")
