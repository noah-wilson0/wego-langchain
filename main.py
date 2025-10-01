import uvicorn
from fastapi import FastAPI
from routers.generate_initial import router as gen_router
from routers.repair_slot import router as repair_router

app = FastAPI()

# 라우터 등록
app.include_router(gen_router)
app.include_router(repair_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", port=7070, reload=True)
