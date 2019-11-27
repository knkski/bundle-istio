from subprocess import run

import yaml
from charms import layer
from charms.reactive import set_flag, clear_flag, when, when_not, hook, when_any
from pathlib import Path


@hook("upgrade-charm")
def upgrade_charm():
    clear_flag("charm.started")


@when('charm.started')
def charm_ready():
    layer.status.active('')


@when_any('layer.docker-resource.oci-image.changed')
def update_image():
    clear_flag('charm.started')


@when('layer.docker-resource.oci-image.available')
@when_not('charm.started')
def start_charm():
    layer.status.maintenance('configuring container')

    image_info = layer.docker_resource.get_info('oci-image')

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
            'containers': [
                {
                    'name': 'prometheus',
                    'args': [
                        '--storage.tsdb.retention=6h',
                        '--config.file=/etc/prometheus/prometheus.yml',
                    ],
                    'imageDetails': {
                        'imagePath': image_info.registry_path,
                        'username': image_info.username,
                        'password': image_info.password,
                    },
                    'ports': [{'name': 'http', 'containerPort': 9090}],
                    'files': [
                        {
                            'name': 'prometheus',
                            'mountPath': '/etc/prometheus',
                            'files': {'prometheus.yml': Path('files/prometheus.yml').read_text()},
                        },
                        {
                            'name': 'istio-certs',
                            'mountPath': '/etc/istio-certs',
                            'files': {
                                'root-cert.pem': Path('cert.pem').read_text(),
                                'cert-chain.pem': Path('cert.pem').read_text(),
                                'key.pem': Path('key.pem').read_text(),
                            },
                        },
                    ],
                }
            ]
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.started')
