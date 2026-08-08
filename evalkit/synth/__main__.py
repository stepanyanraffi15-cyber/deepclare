"""Enables ``python -m synth …``."""

import sys

from .cli import main

sys.exit(main())
