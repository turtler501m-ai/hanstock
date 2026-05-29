# -*- coding: utf-8 -*-
from fastapi import Body, HTTPException, Request
from fastapi.responses import FileResponse
import src.dashboard.core as _core
from src.dashboard.core import *
globals().update({k: v for k, v in _core.__dict__.items() if not k.startswith('__')})

@app.get("/", response_class=FileResponse)
def read_root():
    return FileResponse(WEB_DIR / "templates" / "index.html")




@app.get("/finrl", response_class=FileResponse)
def read_finrl_dashboard():
    return FileResponse(WEB_DIR / "templates" / "finrl.html")




@app.get("/vendors", response_class=FileResponse)
def read_vendor_dashboard():
    return FileResponse(WEB_DIR / "templates" / "vendors.html")




@app.get("/ai-dashboard", response_class=FileResponse)
def read_ai_dashboard():
    return FileResponse(WEB_DIR / "templates" / "ai_dashboard.html")




@app.get("/ai-dashboard/futures-signals", response_class=FileResponse)
def read_futures_signals_dashboard():
    return FileResponse(WEB_DIR / "templates" / "futures_signals.html")




@app.get("/env-settings", response_class=FileResponse)
def read_env_settings():
    return FileResponse(WEB_DIR / "templates" / "env_settings.html")



