from celery import shared_task

from . import services


@shared_task
def generate_node_content_task(node_id):
    services.generate_node_content(node_id)


@shared_task
def handle_question_task(question_id):
    services.handle_question(question_id)
