import os
from pathlib import Path
from subprocess import run

import yaml

from charmhelpers.core import hookenv
from charms import layer
from charms.reactive import clear_flag, hook, set_flag, when, when_any, when_not


@hook("upgrade-charm")
def upgrade_charm():
    clear_flag("charm.started")


@when("charm.started")
def charm_ready():
    layer.status.active("")


@when("istio-galley.available")
def configure_http(http):
    http.configure(port=9901, hostname=hookenv.application_name())


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
            f"/CN={hookenv.service_name()}.{namespace}.svc",
            "-nodes",
        ],
        check=True,
    )

    mesh = yaml.dump(
        {
            "disablePolicyChecks": False,
            "enableTracing": True,
            "accessLogFile": "/dev/stdout",
            "accessLogFormat": "",
            "accessLogEncoding": "TEXT",
            "mixerCheckServer": f"istio-policy.{namespace}.svc.cluster.local:9091",
            "mixerReportServer": f"istio-telemetry.{namespace}.svc.cluster.local:9091",
            "policyCheckFailOpen": False,
            "ingressService": "istio-ingressgateway",
            "connectTimeout": "10s",
            "dnsRefreshRate": "5s",
            "sdsUdsPath": None,
            "enableSdsTokenMount": False,
            "sdsUseK8sSaJwt": False,
            "trustDomain": None,
            "outboundTrafficPolicy": {"mode": "ALLOW_ANY"},
            "localityLbSetting": {},
            "rootNamespace": namespace,
            "configSources": [{"address": f"istio-galley.{namespace}.svc:9901"}],
            "defaultConfig": {
                "connectTimeout": "10s",
                "configPath": "/etc/istio/proxy",
                "binaryPath": "/usr/local/bin/envoy",
                "serviceCluster": "istio-proxy",
                "drainDuration": "45s",
                "parentShutdownDuration": "1m0s",
                "proxyAdminPort": 15000,
                "concurrency": 2,
                "tracing": {"zipkin": {"address": f"zipkin.{namespace}:9411"}},
                "controlPlaneAuthPolicy": "NONE",
                "discoveryAddress": f"istio-pilot.{namespace}:15010",
            },
        }
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
                            "files": {"mesh": mesh, "meshNetworks": "networks: {}"},
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
            "kubernetesResources": {
                "customResourceDefinitions": {
                    crd["metadata"]["name"]: crd["spec"] for crd in crds
                }
            }
        },
    )

    layer.status.maintenance("creating container")
    set_flag("charm.started")
