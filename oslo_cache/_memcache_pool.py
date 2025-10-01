# Copyright 2014 Mirantis Inc
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""Thread-safe connection pool for python-memcached."""

from collections.abc import Generator
import contextlib
import dataclasses
import itertools
import queue
import threading
import time
from typing import Any, Generic, TypeVar
import warnings

try:
    import eventlet
except ImportError:
    eventlet = None
import memcache
from oslo_log import log

from oslo_cache._i18n import _
from oslo_cache import exception


LOG = log.getLogger(__name__)


if eventlet and eventlet.patcher.is_monkey_patched('thread'):
    warnings.warn(
        "Eventlet support is deprecated and will be removed.",
        category=DeprecationWarning,
        stacklevel=3,
    )


class _MemcacheClient(memcache.Client):  # type: ignore
    """Thread global memcache client

    As client is inherited from threading.local we have to restore object
    methods overloaded by threading.local so we can reuse clients in
    different threads
    """

    __delattr__ = object.__delattr__
    __getattribute__ = object.__getattribute__
    __setattr__ = object.__setattr__

    # Hack for lp 1812935
    if eventlet and eventlet.patcher.is_monkey_patched('thread'):
        # NOTE(bnemec): I'm not entirely sure why this works in a
        # monkey-patched environment and not with vanilla stdlib, but it does.
        def __new__(cls, *args: Any, **kwargs: Any) -> type['_MemcacheClient']:
            return object.__new__(cls)
    else:
        __new__ = object.__new__

    def __del__(self) -> None:
        pass


T = TypeVar('T')


@dataclasses.dataclass
class _PoolItem(Generic[T]):
    ttl: float
    connection: T


# TODO(stephenfin): Make this private so we can eventually fold it into
# MemcacheClientPool, it's sole user.
class ConnectionPool(queue.Queue[T], Generic[T]):
    """Base connection pool class

    This class implements the basic connection pool logic as an abstract base
    class.
    """

    def __init__(
        self,
        maxsize: int,
        unused_timeout: float,
        conn_get_timeout: float | None = None,
    ) -> None:
        """Initialize the connection pool.

        :param maxsize: maximum number of client connections for the pool
        :type maxsize: int
        :param unused_timeout: idle time to live for unused clients (in
                               seconds). If a client connection object has been
                               in the pool and idle for longer than the
                               unused_timeout, it will be reaped. This is to
                               ensure resources are released as utilization
                               goes down.
        :type unused_timeout: int
        :param conn_get_timeout: maximum time in seconds to wait for a
                                 connection. If set to `None` timeout is
                                 indefinite.
        :type conn_get_timeout: int
        """
        super().__init__(maxsize)
        self._unused_timeout = unused_timeout
        self._connection_get_timeout = conn_get_timeout
        self._acquired = 0

    def __del__(self) -> None:
        """Delete the connection pool.

        Destory all connections left in the queue.
        """
        while True:
            # As per https://docs.python.org/3/library/collections.html
            # self.queue.pop() will raise IndexError when no elements are
            # present, ending the while True: loop.
            # The logic loops over all connections in the queue but it does
            # not retry for a single one in case a connection closure fails
            # then it leaves that one and process the next.
            try:
                conn = self.queue.pop().connection
                self._destroy_connection(conn)
            except IndexError:
                break
            except Exception as e:
                self._do_log(
                    LOG.warning, "Unable to cleanup a connection: %s", e
                )

    def _create_connection(self) -> T:
        """Returns a connection instance.

        This is called when the pool needs another instance created.

        :returns: a new connection instance

        """
        raise NotImplementedError

    def _destroy_connection(self, conn: T) -> None:
        """Destroy and cleanup a connection instance.

        This is called when the pool wishes to get rid of an existing
        connection. This is the opportunity for a subclass to free up
        resources and cleanup after itself.

        :param conn: the connection object to destroy

        """
        raise NotImplementedError

    def _do_log(self, level: int, msg: str, *args: Any) -> None:
        if LOG.isEnabledFor(level):
            thread_id = threading.current_thread().ident
            args = (id(self), thread_id) + args
            prefix = 'Memcached pool %s, thread %s: '
            LOG.log(level, prefix + msg, *args)

    def _debug_logger(self, msg: str, *args: Any) -> None:
        self._do_log(log.DEBUG, msg, *args)

    def _trace_logger(self, msg: str, *args: Any) -> None:
        self._do_log(log.TRACE, msg, *args)

    @contextlib.contextmanager
    def acquire(self) -> Generator[T, None, None]:
        self._trace_logger('Acquiring connection')
        self._drop_expired_connections()
        try:
            conn = self.get(timeout=self._connection_get_timeout)
        except queue.Empty:
            raise exception.QueueEmpty(
                _(
                    'Unable to get a connection from pool id %(id)s after '
                    '%(seconds)s seconds.'
                )
                % {'id': id(self), 'seconds': self._connection_get_timeout}
            )
        self._trace_logger('Acquired connection %s', id(conn))
        try:
            yield conn
        finally:
            self._trace_logger('Releasing connection %s', id(conn))
            try:
                super().put(conn, block=False)
            except queue.Full:
                self._trace_logger('Reaping exceeding connection %s', id(conn))
                self._destroy_connection(conn)

    def _qsize(self) -> int:
        if self.maxsize:
            return self.maxsize - self._acquired
        else:
            # A value indicating there is always a free connection
            # if maxsize is None or 0
            return 1

    # NOTE(dstanek): stdlib and eventlet Queue implementations
    # have different names for the qsize method. This ensures
    # that we override both of them.
    # TODO(stephenfin): Remove when we drop eventlet support
    if not hasattr(queue.Queue, '_qsize'):
        qsize = _qsize

    def _get(self) -> T:
        try:
            conn = self.queue.pop().connection
        except IndexError:
            conn = self._create_connection()
        self._acquired += 1
        return conn  # type: ignore

    def _drop_expired_connections(self) -> None:
        """Drop all expired connections from the left end of the queue."""
        now = time.time()
        try:
            while self.queue[0].ttl < now:
                conn = self.queue.popleft().connection
                self._trace_logger('Reaping connection %s', id(conn))
                self._destroy_connection(conn)
        except IndexError:
            # NOTE(amakarov): This is an expected excepton. so there's no
            # need to react. We have to handle exceptions instead of
            # checking queue length as IndexError is a result of race
            # condition too as well as of mere queue depletio of mere queue
            # depletionn.
            pass

    def _put(self, conn: T) -> None:
        self.queue.append(
            _PoolItem(
                ttl=time.time() + self._unused_timeout,
                connection=conn,
            )
        )
        self._acquired -= 1


class MemcacheClientPool(ConnectionPool[_MemcacheClient]):
    def __init__(
        self,
        urls: list[str],
        arguments: dict[str, Any],
        *,
        maxsize: int,
        unused_timeout: float,
        conn_get_timeout: float | None = None,
    ) -> None:
        super().__init__(maxsize, unused_timeout, conn_get_timeout)
        self.urls = urls
        self._arguments = {
            'dead_retry': arguments.get('dead_retry', 5 * 60),
            'socket_timeout': arguments.get('socket_timeout', 3.0),
            'server_max_value_length': arguments.get(
                'server_max_value_length'
            ),
            'flush_on_reconnect': arguments.get(
                'pool_flush_on_reconnect', False
            ),
        }
        # NOTE(morganfainberg): The host objects expect an int for the
        # deaduntil value. Initialize this at 0 for each host with 0 indicating
        # the host is not dead.
        self._hosts_deaduntil = [0] * len(urls)

    def _create_connection(self) -> _MemcacheClient:
        return _MemcacheClient(self.urls, **self._arguments)

    def _destroy_connection(self, conn: _MemcacheClient) -> None:
        conn.disconnect_all()

    def _get(self) -> _MemcacheClient:
        conn = super()._get()
        try:
            # Propagate host state known to us to this client's list
            now = time.time()
            for deaduntil, host in zip(self._hosts_deaduntil, conn.servers):
                if deaduntil > now and host.deaduntil <= now:
                    host.mark_dead('propagating death mark from the pool')
                host.deaduntil = deaduntil
        except Exception:
            # We need to be sure that connection doesn't leak from the pool.
            # This code runs before we enter context manager's try-finally
            # block, so we need to explicitly release it here.
            super()._put(conn)
            raise
        return conn

    def _put(self, conn: _MemcacheClient) -> None:
        try:
            # If this client found that one of the hosts is dead, mark it as
            # such in our internal list
            now = time.time()
            for i, host in zip(itertools.count(), conn.servers):
                deaduntil = self._hosts_deaduntil[i]
                # Do nothing if we already know this host is dead
                if deaduntil <= now:
                    if host.deaduntil > now:
                        self._hosts_deaduntil[i] = host.deaduntil
                        self._debug_logger(
                            'Marked host %s dead until %s',
                            self.urls[i],
                            host.deaduntil,
                        )
                    else:
                        self._hosts_deaduntil[i] = 0
        finally:
            super()._put(conn)
