import sys
import time
import bubblesub.util
import importlib.util


class classproperty(property):
    def __get__(self, cls, owner):
        return classmethod(self.fget).__get__(None, owner)()


class BaseCommand:
    def __init__(self, api):
        self.api = api

    @classproperty
    def name(cls):
        raise NotImplementedError('Command has no name')

    def enabled(self):
        return True

    def run(self, text):
        raise NotImplementedError('Command has no implementation')

    def debug(self, text):
        self.api.log.debug('cmd/{}: '.format(self.name, text))

    def info(self, text):
        self.api.log.info('cmd/{}: {}'.format(self.name, text))

    def warn(self, text):
        self.api.log.warn('cmd/{}: {}'.format(self.name, text))

    def error(self, text):
        self.api.log.error('cmd/{}: {}'.format(self.name, text))

    def log(self, level, text):
        self.logged.emit(level, text)


class CommandApi:
    core_registry = {}
    plugin_registry = {}

    def __init__(self, api):
        self._api = api

    def run(self, cmd, cmd_args):
        if cmd.enabled():
            self._api.log.info('cmd/{}: running...'.format(cmd.name))
            start_time = time.time()
            cmd.run(*cmd_args)
            end_time = time.time()
            self._api.log.info('cmd/{}: ran in {:.02f} s'.format(
                cmd.name, end_time - start_time))
        else:
            self._api.log.info('cmd/{}: not available right now', cmd.name)

    def get(self, name):
        ret = self.plugin_registry.get(name)
        if not ret:
            ret = self.core_registry.get(name)
        if not ret:
            raise KeyError('No command named {}'.format(name))
        try:
            return ret(self._api)
        except:
            print('Error creating command {}'.format(name), file=sys.stderr)
            raise

    def load_plugins(self, path):
        self.plugin_registry.clear()
        if not path.exists():
            return
        for subpath in path.glob('*.py'):
            spec = importlib.util.spec_from_file_location(
                'bubblesub.plugin', subpath)
            if spec is None:
                continue
            spec.loader.exec_module(importlib.util.module_from_spec(spec))


class CoreCommand(BaseCommand):
    def __init_subclass__(cls):
        CommandApi.core_registry[cls.name] = cls


class PluginCommand(BaseCommand):
    def __init_subclass__(cls):
        CommandApi.plugin_registry[cls.name] = cls