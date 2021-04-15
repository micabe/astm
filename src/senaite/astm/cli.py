# -*- coding: utf-8 -*-

import argparse
import asyncio
import contextlib
import logging
import os
import sys
from datetime import datetime
from time import sleep
from senaite.astm.utils import get_astm_wrappers

from senaite.astm import lims
from senaite.astm import logger
from senaite.astm.decode import decode_message
from senaite.astm.protocol import ASTMProtocol


async def consume(queue, callback=None):
    """ASTM Message consumer coroutine function
    """
    while True:
        message = await queue.get()
        if callable(callback):
            callback(message)


def write_messages(messages, path, ext=".txt"):
    """Write ASTM Messages to file
    """
    now = datetime.now()
    sender_name = get_instrument_sender_name(messages)
    timestamp = now.strftime("%Y-%m-%d_%H:%M:%S")
    filename = "{}".format(timestamp)
    if sender_name:
        filename = "{}-{}".format(sender_name, timestamp)
    filename = "{}{}".format(filename, ext)
    with open(os.path.join(path, filename), "wb") as f:
        f.writelines(messages)


def get_instrument_sender_name(messages):
    """Extract the instrument sender name from the message

    See Section 6: Header Record
    """
    header = messages[0]
    seq, records, cs = decode_message(header)
    sender_name = records[0][4]
    if not sender_name:
        return ""
    return sender_name[0]


def post_to_senaite(messages, session, **kwargs):
    """POST ASTM message to SENAITE
    """
    attempt = 1
    retries = kwargs.get('retries', 3)
    delay = kwargs.get('delay', 5)
    consumer = kwargs.get('consumer', 'senaite.lis2a.import')
    name = get_instrument_sender_name(messages)
    wrappers = kwargs.get('wrappers', {})
    parsed = None
    wrapper_cls = wrappers.get(name.lower())
    if wrapper_cls:
        wrapper = wrapper_cls(messages)
        parsed = wrapper.to_json()

    success = False
    # Build the POST payload
    payload = {
        'consumer': consumer,
        'messages': messages,
        'json': parsed,
    }

    while True:
        # Open a session with SENAITE and authenticate
        authenticated = session.auth()
        if authenticated:
            # Send the message
            response = session.post('push', payload)
            success = response.get('success')
            if success:
                break

        # the break here ensures that at least one time is tried
        if attempt >= retries:
            break

        # increase attempts
        attempt += 1

        logger.warn('Could not push. Retrying {}/{}'.format(
            attempt, retries))

        # Sleep before we retry
        sleep(delay)

    if not success:
        logger.error('Could not push the message')


def main():
    # Argument parser
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Argument groups
    astm_group = parser.add_argument_group('ASTM SERVER')
    lims_group = parser.add_argument_group('SENAITE LIMS')

    astm_group.add_argument(
        '-l',
        '--listen',
        type=str,
        default='0.0.0.0',
        help='Listen IP address')

    astm_group.add_argument(
        '-p',
        '--port',
        type=str,
        default='4010',
        help='Port to connect')

    astm_group.add_argument(
        '-o',
        '--output',
        type=str,
        help='Output directory to write ASTM files')

    lims_group.add_argument(
        '-u',
        '--url',
        type=str,
        help='SENAITE URL address including username and password in the '
             'format: http(s)://<user>:<password>@<senaite_url>')

    lims_group.add_argument(
        '-c',
        '--consumer',
        type=str,
        default='senaite.lis2a.import',
        help='SENAITE push consumer interface')

    lims_group.add_argument(
        '-r',
        '--retries',
        type=int,
        default=3,
        help='Number of attempts of reconnection when SENAITE '
             'instance is not reachable. Only has effect when '
             'argument --url is set')

    lims_group.add_argument(
        '-d',
        '--delay',
        type=int,
        default=5,
        help='Time delay in seconds between retries when '
             'SENAITE instance is not reachable. Only has '
             'effect when argument --url is set')

    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Verbose logging')

    # Parse Arguments
    args = parser.parse_args()

    # Get the current event loop.
    loop = asyncio.get_event_loop()

    # Set logging
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())

    # Validate output path
    output = args.output
    if output and not os.path.isdir(args.output):
        logger.error('Output path must be an existing directory')
        return sys.exit(-1)

    # Validate SENAITE URL
    url = args.url
    if url:
        session = lims.Session(url)
        logger.info('Checking connection to SENAITE ...')
        if not session.auth():
            return sys.exit(-1)

    astm_wrappers = get_astm_wrappers(directories=["instruments"])

    def dispatch_astm_messages(messages):
        """Dispatch astm messages
        """
        logger.debug('Dispatching ASTM Messages')
        if output:
            path = os.path.abspath(output)
            loop.create_task(
                asyncio.to_thread(
                    write_messages, messages, path))
        if url:
            session = lims.Session(url)
            session_args = {
                'delay': args.delay,
                'retries': args.retries,
                'consumer': args.consumer,
                'wrappers': astm_wrappers
            }
            loop.create_task(
                asyncio.to_thread(
                    post_to_senaite, messages, session, **session_args))

    # Bridges communication between the protocol and server
    queue = asyncio.Queue()

    # Create a TCP server coroutine listening on port of the host address.
    server_coro = loop.create_server(
        lambda: ASTMProtocol(loop, queue), host=args.listen, port=args.port)

    # Run until the future (an instance of Future) has completed.
    server = loop.run_until_complete(server_coro)

    for socket in server.sockets:
        ip, port = socket.getsockname()
        logger.info('Starting server on {}:{}'.format(ip, port))
        logger.info('ASTM server ready to handle connections ...')

    # Create a ASTM message consumer task to be scheduled concurrently.
    loop.create_task(consume(queue, callback=dispatch_astm_messages))

    # Run the event loop until stop() is called.
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info('Shutting down server...')
        all_tasks = asyncio.gather(
            *asyncio.all_tasks(loop), return_exceptions=True)
        all_tasks.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            loop.run_until_complete(all_tasks)
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        loop.close()
        logger.info('Server is now down...')


if __name__ == '__main__':
    main()
