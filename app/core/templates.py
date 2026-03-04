from __future__ import annotations
import datetime

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

# Register globals
templates.env.globals["getattr"] = getattr
templates.env.globals["hasattr"] = hasattr
templates.env.globals["now"] = datetime.datetime.now

# Register filters
import json
templates.env.filters["tojson"] = lambda v, indent=None: json.dumps(v, indent=indent)
