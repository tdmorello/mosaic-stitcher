'''General utility functions'''

import logging
import subprocess
import shlex
import time

logger = logging.getLogger(__name__)


def run_command(command: str) -> int:
    '''Runs the given command string as a subprocess

    :param command: shell command to be run
    :type command: str
    :return: exit status of shell command
    :rtype: int
    '''
    logger.debug(f'Running command: {command}')
    output = subprocess.run(shlex.split(command), capture_output=True)
    return_code = output.returncode
    return return_code


def func_timer(func):
    '''Decorator to time'''
    def wrapped_func(*args, **kwargs):
        start_time = time.perf_counter()
        func(*args, **kwargs)
        end_time = time.perf_counter()
        print(f'Completed in {end_time - start_time}s')
    return wrapped_func
