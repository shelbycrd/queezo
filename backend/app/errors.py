"""Request error format shared by the independently runnable APIs."""
from fastapi.responses import JSONResponse


async def validation_error(_, exc):
    details = [{"field": ".".join(str(x) for x in error["loc"]), "message": error["msg"]}
               for error in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {
        "message": "Please check the submitted fields.", "details": details}})
