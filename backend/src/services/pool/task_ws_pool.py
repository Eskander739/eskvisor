import asyncio

import orjson
import websockets
from websockets import State, ConnectionClosed

from src.constants import WS_POOL_SIZE
from src.db.clusters import ClustersDB
from src.models.general import NodeWebsocketConnections
from src.services.pool.db_pool import DBPool


class TaskWebsocketPool:
    def __init__(self, db_pool_instance: DBPool, connection_count: int = WS_POOL_SIZE):
        self.uri_startswith = "ws://{}/ws/task"
        self.connection_count = connection_count
        self.__connections = []
        self.clusters_db = ClustersDB(db_pool_instance)

    async def create_connections(self):
        cluster_list = await self.clusters_db.get_cluster_list()
        if cluster_list is not None:
            for cluster in cluster_list:
                for node in cluster.nodes:
                    try:
                        # Создаем очередь для узла
                        connections_queue = asyncio.Queue(maxsize=self.connection_count)

                        for _ in range(self.connection_count):
                            connect = await websockets.connect(
                                self.uri_startswith.format(node.ip_address)
                            )

                            await connections_queue.put(connect)  # Помещаем в очередь

                        self.__connections.append(
                            NodeWebsocketConnections(
                                cluster_id=cluster.id,
                                node_id=node.id,
                                connections_queue=connections_queue,  # Храним очередь!
                                ip_address=node.ip_address,
                            )
                        )
                    except Exception:
                        pass

    async def close_all(self):
        for node_conn in self.__connections:
            connections_queue = node_conn.connections_queue
            for _ in range(self.connection_count):
                connection = await connections_queue.get()
                await connection.close()

    async def send_json(self, cluster_id: int, node_id: int, data: dict | str):
        for node_connection in self.__connections:
            if (
                node_connection.cluster_id == cluster_id
                and node_connection.node_id == node_id
            ):
                connection = await node_connection.connections_queue.get()

                if connection.state in (State.CLOSED, State.CLOSING):
                    connection = await websockets.connect(
                        self.uri_startswith.format(node_connection.ip_address)
                    )
                try:
                    if isinstance(data, str):
                        await connection.send(data)
                    else:
                        await connection.send(orjson.dumps(data))
                    await node_connection.connections_queue.put(connection)
                except ConnectionClosed:
                    if connection.state not in (State.CLOSED, State.CLOSING):
                        await connection.close()
                    new_connection = await websockets.connect(
                        self.uri_startswith.format(node_connection.ip_address)
                    )
                    await node_connection.connections_queue.put(new_connection)
                    raise

                return


# async def main():
#     pool = TaskWebsocketPool()
#     await pool._create_connections()
# if __name__ == "__main__":
#     # pool = TaskWebsocketPool()
#     asyncio.run(main())
#     # pool.get_connection(1, 2)
