from abc import abstractmethod
import ast
from etcd import EtcdKeyNotFound
import importlib
import inspect
import os
import six

from tendrl.commons.event import Event
from tendrl.commons.message import ExceptionMessage
from tendrl.commons.message import Message
from tendrl.performance_monitoring import constants as \
    pm_consts
from tendrl.performance_monitoring.utils import list_modules_in_package_path
from tendrl.performance_monitoring.utils import read as etcd_read_key


class NoSDSPluginException(Exception):
    pass


class PluginMount(type):

    def __init__(cls, name, bases, attrs):
        if not hasattr(cls, 'plugins'):
            cls.plugins = []
        else:
            cls.register_plugin(cls)

    def register_plugin(cls, plugin):
        instance = plugin()
        cls.plugins.append(instance)


@six.add_metaclass(PluginMount)
class SDSPlugin(object):
    name = ''

    def __init__(self):
        self.supported_services = [
            'tendrl-node-agent',
            'etcd'
        ]

    @abstractmethod
    def configure_monitoring(self, sds_tendrl_context):
        raise NotImplementedError(
            "The plugins overriding SDSPlugin should mandatorily override this"
        )

    @abstractmethod
    def get_cluster_summary(self, cluster_id, cluster_det):
        raise NotImplementedError(
            "The plugins overriding SDSPlugin should mandatorily override this"
        )

    @abstractmethod
    def compute_system_summary(self, cluster_summaries, clusters):
        raise NotImplementedError(
            "The plugins overriding SDSPlugin should mandatorily override this"
        )

    def get_clusters_status_wise_counts(self, clusters):
        clusters_status_wise_counts = {'total': 0}
        for cluster_id, cluster_det in clusters.iteritems():
            if (
                self.name in
                    cluster_det.get('TendrlContext', {}).get('sds_name')
            ):
                cluster_status = cluster_det.get(
                    'GlobalDetails', {}
                ).get('status')
                if cluster_status:
                    if cluster_status not in clusters_status_wise_counts:
                        clusters_status_wise_counts[cluster_status] = 1
                    else:
                        clusters_status_wise_counts[cluster_status] = \
                            clusters_status_wise_counts[cluster_status] + 1
                    clusters_status_wise_counts['total'] = \
                        clusters_status_wise_counts['total'] + 1
        return clusters_status_wise_counts

    def get_system_utilization(self, cluster_summaries):
        net_utilization = {
            'total': 0,
            'used': 0,
            'percent_used': 0
        }
        for cluster_summary in cluster_summaries:
            if self.name in cluster_summary.sds_type:
                net_utilization['total'] = \
                    net_utilization['total'] + int(
                        cluster_summary.utilization.get(
                            'total', 0
                        )
                )
                net_utilization['used'] = \
                    net_utilization['used'] + int(
                        cluster_summary.utilization.get(
                            'used', 0
                        )
                )
                net_utilization['percent_used'] = 0
                if net_utilization['total'] > 0:
                    net_utilization['percent_used'] = (
                        net_utilization['used'] * 100
                    ) / (
                        net_utilization['total'] * 1.0
                    )
        # Push the computed system utilization to time-series db
        NS.time_series_db_manager.get_plugin().push_metrics(
            NS.time_series_db_manager.get_timeseriesnamefromresource(
                sds_type=self.name,
                utilization_type=pm_consts.TOTAL,
                resource_name=pm_consts.SYSTEM_UTILIZATION
            ),
            net_utilization[pm_consts.TOTAL]
        )
        NS.time_series_db_manager.get_plugin().push_metrics(
            NS.time_series_db_manager.get_timeseriesnamefromresource(
                sds_type=self.name,
                utilization_type=pm_consts.USED,
                resource_name=pm_consts.SYSTEM_UTILIZATION
            ),
            net_utilization[pm_consts.USED]
        )
        NS.time_series_db_manager.get_plugin().push_metrics(
            NS.time_series_db_manager.get_timeseriesnamefromresource(
                sds_type=self.name,
                utilization_type=pm_consts.PERCENT_USED,
                resource_name=pm_consts.SYSTEM_UTILIZATION
            ),
            net_utilization[pm_consts.PERCENT_USED]
        )
        return net_utilization

    def get_system_host_status_wise_counts(self, cluster_summaries):
        status_wise_count = {
            'total': 0,
            'down': 0,
            'crit_alert_count': 0,
            'warn_alert_count': 0
        }
        for cluster_summary in cluster_summaries:
            if self.name in cluster_summary.sds_type:
                for status, counter in cluster_summary.hosts_count.iteritems():
                    status_wise_count[status] = \
                        status_wise_count.get(status, 0) + int(counter)
        return status_wise_count

    def get_services_count(self, cluster_det):
        node_service_counts = {}
        for node_id, node_det in cluster_det.get('nodes', {}).iteritems():
            services = etcd_read_key('nodes/%s/Service' % node_id)
            for service_name, service_det in services.iteritems():
                if service_name in self.supported_services:
                    if service_name not in node_service_counts:
                        service_counter = {'running': 0, 'not_running': 0}
                    else:
                        service_counter = node_service_counts[service_name]
                    if service_det['exists'] == 'True':
                        if service_det['running'] == 'True':
                            service_counter['running'] = \
                                service_counter['running'] + 1
                        else:
                            service_counter['not_running'] = \
                                service_counter['not_running'] + 1
                        node_service_counts[service_name] = service_counter
        return node_service_counts

    def get_system_services_count(self, cluster_summaries):
        system_services_count = {}
        for cluster_summary in cluster_summaries:
            if self.name in cluster_summary.sds_type:
                services_count = cluster_summary.sds_det.get('services_count')
                if isinstance(services_count, basestring):
                    services_count = ast.literal_eval(
                        services_count.encode('ascii', 'ignore')
                    )
                for service_name, service_status_counter in \
                        services_count.iteritems():
                    service_counter = {}
                    for service_status, counter in \
                            service_status_counter.iteritems():
                        service_counter[service_status] = \
                            service_counter.get(
                                service_status, 0
                        ) + int(counter)
                    system_services_count[service_name] = service_counter
        return system_services_count


class SDSMonitoringManager(object):
    def load_sds_plugins(self):
        path = os.path.dirname(os.path.abspath(__file__))
        pkg = 'tendrl.performance_monitoring.sds'
        sds_plugins = list_modules_in_package_path(path, pkg)
        for name, sds_fqdn in sds_plugins:
            mod = importlib.import_module(sds_fqdn)
            clsmembers = inspect.getmembers(mod, inspect.isclass)
            for name, cls in clsmembers:
                if issubclass(cls, SDSPlugin):
                    if cls.name:
                        self.supported_sds.append(cls.name)

    def __init__(self):
        self.supported_sds = []
        self.load_sds_plugins()

    def get_cluster_summary(self, cluster_id, cluster_det):
        sds_name = cluster_det.get('TendrlContext', {}).get('sds_name')
        for plugin in SDSPlugin.plugins:
            if plugin.name == sds_name:
                return plugin.get_cluster_summary(cluster_id, cluster_det)

    def compute_system_summary(self, cluster_summaries, clusters):
        for plugin in SDSPlugin.plugins:
            plugin.compute_system_summary(cluster_summaries, clusters)

    def configure_monitoring(self, integration_id):
        try:
            sds_tendrl_context = etcd_read_key(
                'clusters/%s/TendrlContext' % integration_id
            )
        except EtcdKeyNotFound:
            return None
        except Exception as ex:
            Event(
                ExceptionMessage(
                    priority="error",
                    publisher=NS.publisher_id,
                    payload={"message": 'Failed to configure monitoring for '
                                        'cluster %s as tendrl context could '
                                        'not be fetched.' % integration_id,
                             "exception": ex
                             }
                )
            )
            return
        for plugin in SDSPlugin.plugins:
            if plugin.name == sds_tendrl_context['sds_name']:
                return plugin.configure_monitoring(sds_tendrl_context)
        Event(
            Message(
                priority="error",
                publisher=NS.publisher_id,
                payload={"message": 'No plugin defined for %s. Hence cannot '
                                    'configure it' %
                                    sds_tendrl_context['sds_name']
                         }
            )
        )
        return None
