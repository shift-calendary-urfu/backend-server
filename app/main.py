from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

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




# ------------------



# ----- endpoint for health check -----
@app.get(
      "/",
      tags=["Health Check"],
)
async def root():
   return {"message": 'Hello World'}
# -------------------------------------
