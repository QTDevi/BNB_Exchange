import os
from django.core.asgi import get_asgi_application

# from channels.auth import AuthMiddlewareStack
# from channels.routing import ProtocolTypeRouter, URLRouter
# from django.urls import path
# from control.consumers import TokenConsumer

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')


application = get_asgi_application()

# application = ProtocolTypeRouter({
#     "http": get_asgi_application(),
#     "websocket": AuthMiddlewareStack(
#         URLRouter([
#             path('ws/token/', TokenConsumer.as_asgi()),
#         ])
#     ),
# })
