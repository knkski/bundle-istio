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
            "serviceAccount": {
                "global": True,
                "rules": [
                    {
                        "apiGroups": [""],
                        "resources": ["configmaps"],
                        "verbs": ["get", "list", "watch"],
                    },
                    {
                        "apiGroups": ["admissionregistration.k8s.io"],
                        "resources": ["mutatingwebhookconfigurations"],
                        "verbs": ["get", "list", "watch", "patch"],
                    },
                ],
            },
            "containers": [
                {
                    "name": "sidecar-injector-webhook",
                    "args": [
                        "--caCertFile=/etc/istio/certs/root-cert.pem",
                        "--tlsCertFile=/etc/istio/certs/cert-chain.pem",
                        "--tlsKeyFile=/etc/istio/certs/key.pem",
                        "--injectConfig=/etc/istio/inject/config",
                        "--meshConfig=/etc/istio/config/mesh",
                        "--healthCheckInterval=2s",
                        "--healthCheckFile=/health",
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
                            "name": "config-volume",
                            "mountPath": "/etc/istio/config",
                            "files": {
                                "mesh": yaml.dump(
                                    {
                                        "disablePolicyChecks": True,
                                        "reportBatchMaxEntries": 100,
                                        "reportBatchMaxTime": "1s",
                                        "enableTracing": True,
                                        "accessLogFile": "",
                                        "accessLogFormat": "",
                                        "accessLogEncoding": "TEXT",
                                        "enableEnvoyAccessLogService": False,
                                        "mixerCheckServer": f"istio-policy.{namespace}.svc.cluster.local:15004",
                                        "mixerReportServer": f"istio-telemetry.{namespace}.svc.cluster.local:15004",
                                        "policyCheckFailOpen": False,
                                        "ingressService": "istio-ingressgateway",
                                        "connectTimeout": "10s",
                                        "protocolDetectionTimeout": "100ms",
                                        "dnsRefreshRate": "300s",
                                        "sdsUdsPath": "unix:/var/run/sds/uds_path",
                                        "trustDomain": "",
                                        "outboundTrafficPolicy": {"mode": "ALLOW_ANY"},
                                        "localityLbSetting": {"enabled": True},
                                        "rootNamespace": namespace,
                                        "configSources": [
                                            {
                                                "address": f"istio-galley.{namespace}.svc:9901",
                                                "tlsSettings": {"mode": "ISTIO_MUTUAL"},
                                            }
                                        ],
                                        "defaultConfig": {
                                            "connectTimeout": "10s",
                                            "configPath": "/etc/istio/proxy",
                                            "binaryPath": "/usr/local/bin/envoy",
                                            "serviceCluster": "istio-proxy",
                                            "drainDuration": "45s",
                                            "parentShutdownDuration": "1m0s",
                                            "proxyAdminPort": 15000,
                                            "concurrency": 2,
                                            "tracing": {
                                                "zipkin": {
                                                    "address": f"zipkin.{namespace}:9411"
                                                }
                                            },
                                            "controlPlaneAuthPolicy": "MUTUAL_TLS",
                                            "discoveryAddress": f"istio-pilot.{namespace}:15011",
                                        },
                                    }
                                ),
                                "meshNetworks": "networks: {}",
                            },
                        },
                        {
                            "name": "certs",
                            "mountPath": "/etc/istio/certs",
                            "files": {
                                "root-cert.pem": Path("cert.pem").read_text(),
                                "cert-chain.pem": Path("cert.pem").read_text(),
                                "key.pem": Path("key.pem").read_text(),
                            },
                        },
                        {
                            "name": "inject",
                            "mountPath": "/etc/istio/inject",
                            "files": {
                                "config": Path("files/inject-config.yaml").read_text(),
                                "values": Path("files/inject-values.json").read_text(),
                            },
                        },
                    ],
                }
            ],
        }
    )

    layer.status.maintenance("creating container")
    set_flag("charm.started")
