import asyncio
import time

import orjson
import websockets

from src.models.general import SystemStatRequest, ObjectStatEnum


async def send_and_receive(uri: str = "", message: str = ""):
    if not uri.startswith("ws://"):
        raise ValueError("Некорректный формат подключения")
    # uri = "ws://192.168.100.134/ws/notification"
    async with websockets.connect(uri) as websocket:
        await websocket.send(message)


async def always_listen(uri: str = ""):
    # if not uri.startswith("ws://"):
    #     raise ValueError("Некорректный формат подключения")
    uri = "ws://192.168.100.134/ws/system-stats"
    websocket = await websockets.connect(uri)
    print(type(websocket))
    while True:
        # await websocket.send(orjson.dumps({"object": "system"}))
        await websocket.send(
            SystemStatRequest(
                cluster_id=1, node_id=2, object=ObjectStatEnum.system
            ).model_dump_json()
        )
        # await websocket.send(orjson.dumps({"object": "system"}).decode("utf-8"))
        response = await websocket.recv()
        print(f"Получено: {response}")


async def main():
    # Запускаем клиент
    await always_listen()


if __name__ == "__main__":
    asyncio.run(main())
