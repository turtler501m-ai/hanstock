# -*- coding: utf-8 -*-
# Backward compatibility facade for src.dashboard
import src.dashboard as _pkg
from src.dashboard import *

# Dynamically expose all names from the package
globals().update({k: v for k, v in _pkg.__dict__.items() if not k.startswith("__")})
