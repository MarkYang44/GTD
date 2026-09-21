"""Project-local direct networking, including spawned download helpers."""
import os


def configure_direct_network():
    # Only this process and its children change; shell/system settings stay intact.
    for name in tuple(os.environ):
        if name.lower() in {'http_proxy', 'https_proxy', 'all_proxy', 'ftp_proxy'}:
            os.environ.pop(name, None)
    os.environ['NO_PROXY'] = '*'
    os.environ['no_proxy'] = '*'


configure_direct_network()
