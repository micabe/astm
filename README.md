# SENAITE ASTM

Middleware to communicate between SENAITE and clinical and laboratory
instruments using ASTM specifications.

This program uses Python `asyncio` to receive ASTM messages on a given IP and
Port. `asyncio` is a library to write concurrent code using the async/await
syntax and needs therefore requires Python 3.6.x or higher.

## Installation

This package can be installed with `pip` from the sources:

    $ git clone git@github.com:senaite/senaite.astm.git
    $ cd senaite.astm
    $ pip install -e .

## Usage

The script `senaite-astm-server` allows to start the server:

    $ senaite-astm-server --help

    usage: senaite-astm-server [-h] [-l LISTEN] [-p PORT] [-o OUTPUT] [-u URL] [-c CONSUMER] [-r RETRIES] [-d DELAY] [-v]

    optional arguments:
      -h, --help            show this help message and exit
      -v, --verbose         Verbose logging (default: False)

    ASTM SERVER:
      -l LISTEN, --listen LISTEN
                            Listen IP address (default: 0.0.0.0)
      -p PORT, --port PORT  Port to connect (default: 4010)
      -o OUTPUT, --output OUTPUT
                            Output directory to write ASTM files (default: None)

    SENAITE LIMS:
      -u URL, --url URL     SENAITE URL address including username and password in the format:
                            http(s)://<user>:<password>@<senaite_url> (default: None)
      -c CONSUMER, --consumer CONSUMER
                            SENAITE push consumer interface (default: senaite.lis2a.import)
      -r RETRIES, --retries RETRIES
                            Number of attempts of reconnection when SENAITE instance is not reachable. Only has effect
                            when argument --url is set (default: 3)
      -d DELAY, --delay DELAY
                            Time delay in seconds between retries when SENAITE instance is not reachable. Only has
                            effect when argument --url is set (default: 5**

**Note ☝️:**
The push consumer endpoint `senaite.lis2a.import` does currently not support the
full messages (including control characters) sent by `senaite.astm`.
Therefore, it requires to register a custom endpoint for doing the results import.

## Commands

```
senaite-astm-server -u http://admin:password@localhost:8081/senaite
senaite-astm-send -u http://admin:password@localhost:8081/senaite -i src/senaite/astm/data/cobas.txt
```

## Errors

```
Traceback (most recent call last):
  File "/home/senaite/buildout-cache/eggs/cp27mu/plone.jsonapi.core-0.7.0-py2.7.egg/plone/jsonapi/core/browser/decorators.py", line 23, in decorator
    return f(*args, **kwargs)
  File "/home/senaite/buildout-cache/eggs/cp27mu/plone.jsonapi.core-0.7.0-py2.7.egg/plone/jsonapi/core/browser/api.py", line 57, in to_json
    return self.dispatch()
  File "/home/senaite/buildout-cache/eggs/cp27mu/plone.jsonapi.core-0.7.0-py2.7.egg/plone/jsonapi/core/browser/api.py", line 51, in dispatch
    return router(self.context, self.request, path)
  File "/home/senaite/buildout-cache/eggs/cp27mu/plone.jsonapi.core-0.7.0-py2.7.egg/plone/jsonapi/core/browser/router.py", line 150, in __call__
    return self.view_functions[endpoint](context, request, **values)
  File "/home/senaite/buildout-cache/eggs/cp27mu/senaite.jsonapi-2.3.0-py2.7.egg/senaite/jsonapi/v1/routes/push.py", line 61, in push
    api.fail(500, str(e))
  File "/home/senaite/buildout-cache/eggs/cp27mu/senaite.jsonapi-2.3.0-py2.7.egg/senaite/jsonapi/api.py", line 572, in fail
    raise APIError(status, "{}".format(msg))
APIError: Messages are not LIS2-A compliant

```

## Custom push consumer

A push consumer is registered as an adapter in `configure.zcml`:

    <!-- Adapter to handle instrument pushes -->
    <adapter
      name="custom.lis2a.import"
      factory=".lis2a.PushConsumer"
      provides="senaite.jsonapi.interfaces.IPushConsumer"
      for="*" />

The implementation in the `lis2a` module should look like this:

    from senaite.jsonapi.interfaces import IPushConsumer
    from zope.interface import implementer


    @implementer(IPushConsumer)
    class PushConsumer(object):
        """Adapter that handles push requests for name "custom.lis2a.import"
        """
        def __init__(self, data):
            self.data = data

        def process(self):
            """Processes the LIS2-A compliant message.
            """
            # Extract LIS2-A messages from the data
            messages = self.data.get("messages")

            # parse and import the messages ...

            return True
