# import json
# from channels.generic.websocket import AsyncWebsocketConsumer
# from .utils import token_data
#
#
# class TokenConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         await self.accept()
#
#     async def disconnect(self, close_code):
#         await self.close()
#
#     async def receive(self, text_data):
#         data = json.loads(text_data)
#         token_address = data.get('token_address')
#         pair_contract = data.get('pair_contract')
#         token_context = token_data(token_address, pair_contract)
#         await self.send(text_data=json.dumps(token_context))
