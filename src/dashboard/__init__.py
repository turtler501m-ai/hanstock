# -*- coding: utf-8 -*-
from src.dashboard.core import app

# Import all route modules so decorators register on app
import src.dashboard.routes.pages as pages
import src.dashboard.routes.account as account
import src.dashboard.routes.futures as futures
import src.dashboard.routes.quantconnect as quantconnect
import src.dashboard.routes.settings as settings
import src.dashboard.routes.stock as stock

# Dynamically expose all names from core and all route files for backward compatibility
import src.dashboard.core as _core

for mod in [_core, pages, account, futures, quantconnect, settings, stock]:
    globals().update({k: v for k, v in mod.__dict__.items() if not k.startswith("__")})