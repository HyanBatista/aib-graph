from django.contrib import admin

from .models import GraphEdge, GraphNode, NodeProgress, StudentQuestion

admin.site.register(GraphNode)
admin.site.register(GraphEdge)
admin.site.register(NodeProgress)
admin.site.register(StudentQuestion)
