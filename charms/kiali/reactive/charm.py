import os

import yaml
from charms import layer
from charms.reactive import set_flag, clear_flag, when, when_not, hook, when_any


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

    layer.caas_base.pod_spec_set(
        {
            "version": 2,
            'containers': [
                {
                    'name': 'kiali',
                    'command': [
                        "/opt/kiali/kiali",
                        "-config",
                        "/kiali-configuration/config.yaml",
                        "-v",
                        "4",
                    ],
                    'imageDetails': {
                        'imagePath': image_info.registry_path,
                        'username': image_info.username,
                        'password': image_info.password,
                    },
                    'config': {
                        'ACTIVE_NAMESPACE': os.environ['JUJU_MODEL_NAME'],
                        'PROMETHEUS_SERVICE_URL': 'http://prometheus:9090',
                        'SERVER_WEB_ROOT': '/kiali',
                    },
                    'files': [
                        {
                            'name': 'configuration',
                            'mountPath': '/kiali-configuration',
                            'files': {
                                'config.yaml': yaml.dump(
                                    {
                                        'external_services': {
                                            'grafana': {'url': None},
                                            'istio': {
                                                'url_service_version': 'http://istio-pilot:8080/version'
                                            },
                                            'jaeger': {'url': None},
                                        },
                                        'istio_namespace': 'istio-system',
                                        'server': {'port': 20001},
                                    }
                                )
                            },
                        },
                        {
                            'name': 'secret',
                            'mountPath': '/kiali-secret',
                            'files': {'username': 'YWRtaW4=', 'passphrase': 'YWRtaW4='},
                        },
                    ],
                }
            ]
        }
    )

    layer.status.maintenance('creating container')
    set_flag('charm.started')
