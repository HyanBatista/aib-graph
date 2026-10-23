from django.contrib import admin

from .models import Book, IndexTopic, TopicRelation

admin.site.register(Book)
admin.site.register(IndexTopic)
admin.site.register(TopicRelation)
