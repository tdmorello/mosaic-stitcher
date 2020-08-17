"""
check that bioformats cli tools are installed
"""

import os
import pathlib
import shlex
import shutil
import subprocess
import sys

# $ export BFTOOLS_PATH=/path/to/bftools
# or set BFTOOLS_PATH here
BFTOOLS_PATH = None

# try to assign bftools_path variable
if BFTOOLS_PATH is not None:
    # get variable definition from script
    bftools_path = pathlib.Path(BFTOOLS_PATH)
else:
    # check environment for variable definition
    # will return KeyError if it is not defined
    try:
        bftools_path = pathlib.Path(os.environ['BFTOOLS_PATH'])
    except KeyError as e:
        print('BFTOOLS_PATH not set... checking shell path')
        bftools_path = None

bftools = {}

# check if bftools path is valid
if bftools_path is not None:
    if bftools_path.exists():
        bftools['bfconvert'] = bftools_path.joinpath('bfconvert')
        bftools['tiffcomment'] = bftools_path.joinpath('tiffcomment')
# see if the shell knows where the commands are
else:
    bftools['bfconvert'] = pathlib.Path(shutil.which('bfconvert'))
    bftools['tiffcomment'] = pathlib.Path(shutil.which('tiffcomment'))
    if None in bftools.values():
        raise FileNotFoundError()

# finally, check if each cli tool works
# TODO check to make sure the output makes sense
for cmd in bftools.values():
    try:
        subprocess.run(shlex.split(str(cmd)), capture_output=True)
        # return codes 0 and 1 mean the command has run

    except FileNotFoundError as e:
        print(f'{cmd} not found exiting', e, sep='\n')
        sys.exit(0)
