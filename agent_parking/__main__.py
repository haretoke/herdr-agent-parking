import os
import sys

from .cli import main

sys.exit(main(sys.argv[1:], dict(os.environ)))
