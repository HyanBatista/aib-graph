from ninja import NinjaAPI

from accounts.api import JWTAuth
from accounts.api import router as auth_router
from assessment.api import router as tests_router
from books.api import router as books_router
from classes.api import router as classes_router
from graph.api import router as graph_router
from metrics.api import router as metrics_router

api = NinjaAPI(title="AIB Graph API", version="1.0.0", auth=JWTAuth())

api.add_router("/auth", auth_router, auth=None)
api.add_router("/classes", classes_router)
api.add_router("/classes", books_router)
api.add_router("/classes", graph_router)
api.add_router("/classes", tests_router)
api.add_router("/classes", metrics_router)
