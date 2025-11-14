import uvicorn
from fastapi import FastAPI
from draftPlan.routers.generate_initial import router as gen_router
from draftPlan.routers.repair_slot import router as repair_router
from travelPlan.routers.edit_travel_plan import router as edit_router




app = FastAPI()

# 라우터 등록
app.include_router(gen_router)
app.include_router(repair_router)

app.include_router(edit_router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", port=7070, reload=True)
