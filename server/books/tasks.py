from celery import shared_task

from . import services


@shared_task
def ingest_book_task(classroom_id):
    services.ingest_book(classroom_id)


@shared_task
def build_graph_task(classroom_id):
    services.build_graph(classroom_id)
