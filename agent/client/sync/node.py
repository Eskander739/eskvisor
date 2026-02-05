import asyncio
import os

import aiohttp
import psutil
import platform
from datetime import datetime

from dotenv import load_dotenv

from agent.client.constants import PROD_ENV
from agent.client.models.general import NodeSyncStateFromAgent

load_dotenv(PROD_ENV)


class NodeStateCollector:
    def __init__(self):
        self.backend_url = os.environ.get("BACKEND_URL")
        if self.backend_url is None:
            raise ValueError("Агент не подключен к бэкэнду")
        self.agent_url = os.environ.get("AGENT_URL")
        if self.agent_url is None:
            raise ValueError("Некорректно настроен агент")
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def get_system_info(self) -> NodeSyncStateFromAgent:
        mem = psutil.virtual_memory()

        total_disk_gb = 0
        free_disk_gb = 0

        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                total_disk_gb += usage.total
                free_disk_gb += usage.free
            except (PermissionError, FileNotFoundError):
                continue

        total_disk_gb = total_disk_gb // (1024**3)
        free_disk_gb = free_disk_gb // (1024**3)

        cpu_model = None
        if platform.system() == "Linux":
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.startswith("model name"):
                            cpu_model = line.split(":")[1].strip()
                            break
            except FileNotFoundError:
                pass

        return NodeSyncStateFromAgent(
            ip_address=self.agent_url,
            hostname=platform.node(),
            cpu_cores=psutil.cpu_count(logical=True),
            cpu_model=cpu_model,
            total_memory_gb=mem.total // (1024**3),
            free_memory_gb=mem.available // (1024**3),
            total_storage_gb=total_disk_gb,
            free_storage_gb=free_disk_gb,
        )

    async def sync_state(self):
        try:
            state_data = self.get_system_info()
            endpoint = "/api/v0/sync/node/sync-state"
            url = "http://" + self.backend_url + endpoint

            async with self.session.post(
                url,
                json=state_data.model_dump(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:

                if response.status == 200:
                    print(f"{datetime.now().isoformat()} - Sync successful")
                else:
                    print(
                        f"{datetime.now().isoformat()} - Sync failed: HTTP {response.status}"
                    )

        except aiohttp.ClientError as e:
            print(f"{datetime.now().isoformat()} - Network error: {e}")
        except Exception as e:
            print(f"{datetime.now().isoformat()} - Error: {e}")


async def main():
    collector = NodeStateCollector()

    async with collector:
        await collector.sync_state()


if __name__ == "__main__":
    asyncio.run(main())
