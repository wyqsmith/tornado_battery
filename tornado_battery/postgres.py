# -*- coding: utf-8 -*-
#
# This piece of code is written by
#    Jianing Yang <jianingy.yang@gmail.com>
# with love and passion!
#
#        H A P P Y    H A C K I N G !
#              _____               ______
#     ____====  ]OO|_n_n__][.      |    |
#    [________]_|__|________)<     |YANG|
#     oo    oo  'oo OOOO-| oo\\_   ~o~~~o~
# +--+--+--+--+--+--+--+--+--+--+--+--+--+
#                             22 Jan, 2016
#
from .exception import ServerException
from .pattern import NamedSingletonMixin
from tornado.options import define, options
from urllib.parse import urlparse

import asyncio
import aiopg
import functools
import logging

LOG = logging.getLogger('tornado.application')


class PostgresConnectorError(ServerException):
    pass


class PostgresConnector(NamedSingletonMixin):

    def __init__(self, name: str):
        self.name = name

    def setup_options(self):
        name = self.name
        opts = options.group_dict('%s database' % name)
        uri = opts[option_name(name, "uri")]
        r = urlparse(uri)
        if r.scheme.lower() != 'postgres':
            raise PostgresConnectorError('%s is not a postgres connection scheme' % uri)
        fmt = ('host={host} port={port} dbname={db} user={user} password={pw}')
        dsn = fmt.format(host=r.hostname or 'localhost',
                         port=r.port or 5432,
                         user=r.username,
                         pw=r.password,
                         db=r.path.lstrip('/') or r.username)
        self._connection_string = dsn
        self._reconnect_interval = opts[option_name(name, "reconnect-interval")]
        self._num_connections = opts[option_name(name, "num-connections")]

    def connection(self):
        if not hasattr(self, '_connections') or not self._connections:
            raise PostgresConnectorError("no connection of %s found" % self.name)
        return self._connections.acquire()

    async def connect(self, event_loop=None):
        self.setup_options()
        LOG.info('connecting postgresql [%s] %s' %
                 (self.name, self._connection_string))
        if event_loop is None:
            event_loop = asyncio.get_event_loop()
        self._connections = await aiopg.create_pool(
            dsn=self._connection_string,
            minsize=int(self._num_connections[0]),
            maxsize=int(self._num_connections[-1]),
            loop=event_loop,
        )
        return self._connections


def option_name(instance: str, option: str) -> str:
    return 'postgres-%s-%s' % (instance, option)


def register_postgres_options(instance: str='master', default_uri: str='postgres:///'):
    define(option_name(instance, "uri"),
           default=default_uri,
           group='%s database' % instance,
           help="postgresql connection uri for %s" % instance)
    define(option_name(instance, 'num-connections'), multiple=True,
           default=[1, 2],
           group='%s database' % instance,
           help='connection pool size for %s ' % instance)
    define(option_name(instance, 'reconnect-interval'),
           default=5,
           group='%s database' % instance,
           help='reconnect interval for %s' % instance)


def with_postgres(name: str):

    def wrapper(function):

        @functools.wraps(function)
        async def f(*args, **kwargs):
            async with PostgresConnector.instance(name).connection() as db:
                if "db" in kwargs:
                    raise PostgresConnectorError(
                        "duplicated database argument for database %s" % name)
                kwargs.update({"db": db})
                retval = await function(*args, **kwargs)
                return retval
        return f

    return wrapper


def connect_postgres(name: str):
    return PostgresConnector.instance(name).connect
