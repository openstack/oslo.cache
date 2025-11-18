=====
Usage
=====

A simple example of oslo.cache in use:

.. code-block:: python

    import time
    from oslo_cache import core as cache
    from oslo_config import cfg

    CONF = cfg.CONF

    # Register cache configuration options
    cache.configure(CONF)

    # Register a custom config group for memoization decorator. The names of
    # these options are important, though the name of the group is not
    caching = cfg.BoolOpt('caching', default=True)
    cache_time = cfg.IntOpt('cache_time', default=3600)
    group = CONF.register_group(cfg.OptGroup('demo'))
    CONF.register_opts([caching, cache_time], group)

    # Load configuration
    CONF()

    # Create cache region
    region = cache.create_region()
    cache.configure_cache_region(CONF, region)

    @region.cache_on_arguments()
    def expensive_operation(name):
        print(f'Running expensive operation for {name}')
        time.sleep(1)
        return f'Hello, {name}!'

    # Create the memoize decorator. This is decorator is very similar to the
    # region.cache_on_arguments except it's configurable via separate
    # configuration group using the 'caching' and 'cache_time' (which we
    # created above). This is useful for differing caching configuration
    # depending on the resources.
    MEMOIZE = cache.get_memoization_decorator(CONF, region, 'demo')

    @MEMOIZE
    def expensive_calculation(x, y):
        print(f'Running an expensive calculation for {x} * {y}...')
        time.sleep(1)
        return x * y

An example config file for this is:

.. code-block:: ini

    [cache]
    enabled = true
    backend = dogpile.cache.memory

    [demo]
    caching = True
    cache_time = 7200

There is some subtlety in the order of the calls in the example above.  The
requirements are: ``configure`` must be done first; ``create_region`` must be
before both ``get_memoization_decorator`` and ``configure_cache_region``
(because they use the output);  the config file must be fully loaded before
``configure_cache_region`` is called; all these calls must complete before a
decorated function is actually invoked.  In principle, there are several
different orders this can happen in.  In practice, the decorator will be used
at import time, and the config file will be loaded later, so the above order is
the only possible one.

Configuring different backends
------------------------------

A variety of backends are available. Configuration examples for these are
provided below. You can use these with the sample application provided above.
For more information on all the options supported by oslo.cache, refer to the
:doc:`configuration guide </configuration/index>`.

.. note::

    These examples also include guidance on how to spin up containers to
    locally test against the backing store. These examples tend to age badly so
    pinned versions are being used: if you are reading this and see a really
    old version of $backend in use, please do test and propose an update!

``oslo_cache.dict``
~~~~~~~~~~~~~~~~~~~

A variant of the ``dogpile.cache.memory`` backend that supports timeouts.

.. code-block:: ini
   :caption: ``dict_conf.ini``

    [cache]
    enabled = true
    backend = oslo_cache.dict
    expiration_time = 600

This runs in memory and needs no other backing service.

``oslo_cache.etcd3gw``
~~~~~~~~~~~~~~~~~~~~~~

Uses etcd as the backing store.

.. code-block:: ini
   :caption: ``etcd_conf.ini``

    [cache]
    enabled = true
    backend = oslo_cache.etcd3gw
    expiration_time = 600
    backend_argument = url:http://localhost:2379

You can start a debug etcd instance using docker:

.. code-block:: shell

    docker run -d \
        --name etcd-oslo-cache \
        -p 2379:2379 \
        gcr.io/etcd-development/etcd:v3.6.1 /usr/local/bin/etcd \
            --advertise-client-urls http://0.0.0.0:2379 \
            --listen-client-urls http://0.0.0.0:2379

``dogpile.cache.memory``
~~~~~~~~~~~~~~~~~~~~~~~~

A simple in-memory cache. Cache eviction is not supported.

.. code-block:: ini
   :caption: ``memory_conf.ini``

    [cache]
    enabled = true
    backend = dogpile.cache.memory
    expiration_time = 600

``dogpile.cache.redis``
~~~~~~~~~~~~~~~~~~~~~~~

Uses redis as the backing store.

.. code-block:: ini
   :caption: ``redis_conf.ini``

    [cache]
    enabled = true
    backend = dogpile.cache.redis
    expiration_time = 600
    backend_argument = host:localhost
    backend_argument = port:6379
    backend_argument = db:0

You can start a debug redis instance using docker:

.. code-block:: shell

    docker run -d \
        --name redis-oslo-cache \
        -p 6379:6379 \
        docker.io/redis:8-alpine
