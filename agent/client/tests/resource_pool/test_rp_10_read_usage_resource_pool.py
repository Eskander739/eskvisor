# import random
# import uuid
#
# import pytest
#
# from agent.client.hypervisor.libvirt.models.msg import CommandMessagesEnum
# from agent.client.hypervisor.libvirt.models.volume.balansir import (
#     ResourcePoolVirtualEdit,
# )
# from agent.client.hypervisor.libvirt.models.volume.resource_pool import (
#     ResourcePoolCreateRequest,
#     StoragePoolType,
# )
#
#
# @pytest.mark.tags(
#     "RP‑10",
#     "Просмотр использования ресурсов пула",
# )
# @pytest.mark.parametrize("storage_type", (StoragePoolType.DIR, StoragePoolType.LOGICAL))
# def test_rp_10_read_resource_pool(
#     resource_pool_session, storage_type, create_running_vm_func
# ):
#     """
#     RP‑10: Просмотр использования ресурсов пула
#
#     Увеличить лимит CPU или памяти для пула. Убедиться, что изменения отражаются в статистике.
#     """
#     vm_info, request_id = create_running_vm_func
#     random_name = None
#     rp_deleted = False
#     request_id = str(uuid.uuid4())
#     try:
#         # TODO: Нужна доработка
#         # ____________________________________Создание пула ресурсов______________
#         random_name = f"RP-TEST-{random.randint(10000, 99999)}"
#         rp_template = ResourcePoolCreateRequest(
#             name=random_name,
#             cpu_limit=2,
#             memory_limit=512,
#             storage_limit=1,
#             pool_type=storage_type,
#         )
#         create_rp_info = resource_pool_session.create_resource_pool(
#             rp_template, request_id
#         )
#         assert create_rp_info.message == CommandMessagesEnum.rp_create_success.value
#         assert create_rp_info.code == CommandMessagesEnum.rp_create_success.name
#         assert create_rp_info.rp_info is not None
#         get_rp_info = resource_pool_session.get_pool_info(random_name, request_id)
#         assert get_rp_info.rp_info.name == random_name
#         assert get_rp_info.rp_info.cpu_limit == rp_template.cpu_limit
#         assert get_rp_info.rp_info.memory_limit_gb == rp_template.memory_limit / 1024
#         assert get_rp_info.rp_info.type.value == storage_type.value
#         if rp_template.pool_type == StoragePoolType.LOGICAL:
#             assert int(get_rp_info.rp_info.capacity_gb) == rp_template.storage_limit
#         # ____________________________________Добавление ВМ в ресурс пул______________
#         add_vm_to_resource_pool = (
#             resource_pool_session.virtual_resource_pool.edit_virtual_resource_pool(
#                 ResourcePoolVirtualEdit(name=random_name, vm_uuid_list=vm_info.uuid)
#             )
#         )
#         assert (
#             add_vm_to_resource_pool.message
#             == CommandMessagesEnum.rp_virtual_edit_success.value
#         ), add_vm_to_resource_pool.note
#         assert (
#             add_vm_to_resource_pool.code
#             == CommandMessagesEnum.rp_virtual_edit_success.name
#         )
#         # ____________________________________Добавление ВМ в ресурс пул______________
#
#     finally:
#         # ______________________________Удаление пула ресурсов(постусловие)_______
#         if not rp_deleted:
#             delete_rp_info = resource_pool_session.delete_resource_pool(
#                 random_name, request_id
#             )
#             assert delete_rp_info.message in (
#                 CommandMessagesEnum.rp_delete_success.value,
#                 CommandMessagesEnum.rp_not_found.value,
#             ), delete_rp_info.note
#             assert delete_rp_info.code in (
#                 CommandMessagesEnum.rp_delete_success.name,
#                 CommandMessagesEnum.rp_not_found.name,
#             )
