import logging
from datetime import datetime
from spaceone.core import config
from spaceone.core.token import get_token
from spaceone.core.manager import BaseManager
from spaceone.inventory.error import *
from spaceone.inventory.model.collector_model import Collector


__ALL__ = ['CollectorManager']

_LOGGER = logging.getLogger(__name__)


class CollectorManager(BaseManager):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.collector_model: Collector = self.locator.get_model('Collector')

    def create_collector(self, params):
        """
        Args: params
          - name
          - plugin_info
          - schedule
          - state
          - tags
          - domain_id
        """
        def _rollback(collector_vo):
            _LOGGER.info(f'[ROLLBACK] Delete collector : {collector_vo.name} ({collector_vo.collector_id})')
            collector_vo.delete()

        collector_vo: Collector = self.collector_model.create(params)
        self.transaction.add_rollback(_rollback, collector_vo)
        return collector_vo

    def delete_collector(self, collector_id, domain_id):
        collector_vo = self.collector_model.get(collector_id=collector_id, domain_id=domain_id)
        collector_vo.delete()

    def get_collector(self, collector_id, domain_id, only=None):
        return self.collector_model.get(collector_id=collector_id, domain_id=domain_id, only=only)

    def enable_collector(self, collector_id, domain_id):
        collector_vo: Collector = self.collector_model.get(collector_id=collector_id, domain_id=domain_id)
        return collector_vo.update({'state': 'ENABLED'})

    def disable_collector(self, collector_id, domain_id, plugin_init=True):
        collector_vo: Collector = self.collector_model.get(collector_id=collector_id, domain_id=domain_id)
        return collector_vo.update({'state': 'DISABLED'})

    def list_collectors(self, query):
        return self.collector_model.query(**query)

    def stat_collectors(self, query):
        return self.collector_model.stat(**query)

    def update_last_collected_time(self, collector_vo):
        """ Update last_updated_time of collector
        """
        params = {'last_collected_at': datetime.utcnow()}
        self.update_collector_by_vo(collector_vo, params)

    @staticmethod
    def update_collector_by_vo(collector_vo, params):
        """ Update collector
        Get collector_vo, then update with this
        """
        return collector_vo.update(params)

    @staticmethod
    def get_queue_name(name='collect_queue'):
        """ Return queue
        """
        try:
            return config.get_global(name)
        except Exception as e:
            _LOGGER.warning(f'[_get_queue_name] name: {name} is not configured')
            return None

    @staticmethod
    def create_task_pipeline(req_params, domain_id):
        """ Create Pipeline Task
        """
        try:
            task = {
                'locator': 'MANAGER',
                'name': 'CollectingManager',
                'metadata': {'token': get_token(), 'domain_id': domain_id},
                'method': 'collecting_resources',
                'params': req_params
            }
            stp = {'name': 'collecting_resources',
                   'version': 'v1',
                   'executionEngine': 'BaseWorker',
                   'stages': [task]
                   }
            _LOGGER.debug(f'[_create_task] tasks: {stp}')
            return stp
        except Exception as e:
            _LOGGER.warning(f'[_create_task] failed asynchronous collect, {e}')
            return None

    @staticmethod
    def _make_collecting_parameters(**kwargs):
        """ Make parameters for collecting_resources

        Args:
            collector_dict
            secret_id
            domain_id
            filter
            job_vo
            job_task_vo
            params

        """

        new_params = {
            'secret_id': kwargs['secret_id'],
            'job_id':    kwargs['job_vo'].job_id,
            'job_task_id':    kwargs['job_task_vo'].job_task_id,
            'domain_id': kwargs['domain_id'],
            'collector_id': kwargs['collector_dict']['collector_id']
        }

        # plugin_info dict
        new_params.update({'plugin_info': kwargs['collector_dict']['plugin_info'].to_dict()})

        # use_cache
        params = kwargs['params']
        use_cache = params.get('use_cache', False)
        new_params.update({'use_cache': use_cache})

        # _LOGGER.debug(f'[_make_collecting_parameters] params: {new_params}')
        return new_params

    @staticmethod
    def is_supported_schedule(plugin_info, schedule):
        """ Check metadata.supported_schedule
        ex) metadata.supported_schedule: ["hours", "interval", "cron"]
        """
        metadata = plugin_info.get('metadata')

        if metadata is None:
            _LOGGER.warning(f'[is_supported_schedule] no metadata: {plugin_info}')
            return True

        supported_schedule = metadata.get('supported_schedules')

        if supported_schedule is None:
            _LOGGER.warning(f'[is_supported_schedule] no schedule: {plugin_info}')
            return True

        requested = schedule.keys()
        if set(requested).issubset(set(supported_schedule)):
            return True

        raise ERROR_UNSUPPORTED_SCHEDULE(supported=supported_schedule, requested=requested)