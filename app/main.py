from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.users.router import router as users_router
from app.workplaces.router import router as workplaces_router
from app.employees.router import router as employees_router

from app.config import settings

# ----- Fast API ----- 
app = FastAPI(
    title="Shift calendary. Server",
    version='0.1.0'
)
# --------------------


# ----- CORSMiddleware -----
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=[
        "GET", 
        "POST", 
        "PUT", 
        "DELETE"
    ],
    allow_headers=[
        "Content-Type",
        "Authorization",
        "Accept",
        "X-Requested-With",
    ],
)
# --------------------------


# ----- Routes -----
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(workplaces_router)
app.include_router(employees_router)

# ------------------



# ----- endpoint for health check -----
@app.get(
    "/",
    tags=["Health Check"],
)
async def root():
   return {"message": 'Hello World'}
# -------------------------------------
