=====
Usage
=====

A simple example of oslo.cache in use::

    from oslo_cache import core as cache
    from oslo_config import cfg

    CONF = cfg.CONF

    caching = cfg.BoolOpt('caching', default=True)
    cache_time = cfg.IntOpt('cache_time', default=3600)
    CONF.register_opts([caching, cache_time], "feature-name")

    cache.configure(CONF)
    example_cache_region = cache.create_region()
    MEMOIZE = cache.get_memoization_decorator(
        CONF, example_cache_region, "feature-name")

    # Load config file here

    cache.configure_cache_region(CONF, example_cache_region)


    @MEMOIZE
    def f(x):
        print(x)
        return x

An example config file for this is::

    [cache]
    enabled = true
    backend = dogpile.cache.memory

    [feature-name]
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
