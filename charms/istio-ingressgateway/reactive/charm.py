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


@when_any("layer.docker-resource.oci-image.changed")
def update_image():
    clear_flag("charm.started")


@when("layer.docker-resource.oci-image.available")
@when_not("charm.started")
def start_charm():
    layer.status.maintenance("configuring container")

    image_info = layer.docker_resource.get_info("oci-image")

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
                    "name": "istio-ingressgateway",
                    "args": [
                        "proxy",
                        "router",
                        "--domain",
                        f"{namespace}.svc.cluster.local",
                        "--log_output_level=default:info",
                        "--drainDuration",
                        "45s",
                        "--parentShutdownDuration",
                        "1m0s",
                        "--connectTimeout",
                        "10s",
                        "--serviceCluster",
                        "istio-ingressgateway",
                        "--zipkinAddress",
                        "zipkin:9411",
                        "--proxyAdminPort",
                        "15000",
                        "--statusPort",
                        "15020",
                        "--controlPlaneAuthPolicy",
                        "NONE",
                        "--discoveryAddress",
                        "istio-pilot:15011",
                    ],
                    "imageDetails": {
                        "imagePath": image_info.registry_path,
                        "username": image_info.username,
                        "password": image_info.password,
                    },
                    "config": {
                        "NODE_NAME": "spec.nodeName",
                        "POD_NAME": "metadata.name",
                        "POD_NAMESPACE": namespace,
                        "INSTANCE_IP": "status.podIP",
                        "HOST_IP": "status.hostIP",
                        "ISTIO_META_POD_NAME": "metadata.name",
                        "ISTIO_META_CONFIG_NAMESPACE": namespace,
                        "SDS_ENABLED": True,
                        "ISTIO_META_WORKLOAD_NAME": "istio-ingressgateway",
                        "ISTIO_META_OWNER": "kubernetes://api/apps/v1/namespaces/$(namespace)/deployments/istio-ingressgateway",
                        "ISTIO_META_ROUTER_MODE": "sni-dnat",
                    },
                    "ports": [
                        {"name": "status-port", "containerPort": 15020},
                        {"name": "http2", "containerPort": 80},
                        {"name": "https", "containerPort": 443},
                        {"name": "tcp", "containerPort": 31400},
                        {"name": "https-kiali", "containerPort": 15029},
                        {"name": "prometheus", "containerPort": 15030},
                        {"name": "grafana", "containerPort": 15031},
                        {"name": "tracing", "containerPort": 15032},
                        {"name": "tls", "containerPort": 15443},
                        {
                            "name": "envoy-prom",
                            "containerPort": 15090,
                            "protocol": "TCP",
                        },
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
                        {
                            "name": "ingressgateway-certs",
                            "mountPath": "/etc/istio/ingressgateway-certs",
                            "files": {
                                "cert-chain.pem": Path("cert.pem").read_text(),
                                "key.pem": Path("key.pem").read_text(),
                            },
                        },
                        {
                            "name": "ingressgateway-ca-certs",
                            "mountPath": "/etc/istio/ingressgateway-ca-certs",
                            "files": {
                                "cert-chain.pem": Path("cert.pem").read_text(),
                                "key.pem": Path("key.pem").read_text(),
                            },
                        },
                    ],
                }
            ]
        }
    )

    layer.status.maintenance("creating container")
    set_flag("charm.started")
