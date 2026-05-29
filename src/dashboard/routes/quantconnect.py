# -*- coding: utf-8 -*-
from fastapi import Body, HTTPException, Request
from fastapi.responses import FileResponse
import src.dashboard.core as _core
from src.dashboard.core import *
globals().update({k: v for k, v in _core.__dict__.items() if not k.startswith('__')})

@app.get("/api/quantconnect/mnq/status")
def get_quantconnect_mnq_status():
    return _quantconnect_mnq_status()




@app.post("/api/quantconnect/mnq/order")
def place_quantconnect_mnq_order(payload: dict = Body(...)):
    return _quantconnect_mnq_order(payload)




@app.post("/api/quantconnect/mnq/deploy")
def deploy_quantconnect_mnq(payload: dict | None = Body(default=None)):
    return _quantconnect_mnq_deploy(payload)



