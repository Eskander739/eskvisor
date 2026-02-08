def convert_vm_state(state_int: int) -> str:
    """
    Конвертирует числовое состояние libvirt в строковое представление.

    Args:
        state_int: Числовое состояние из libvirt (0-7)

    Returns:
        Строковое представление состояния
    """
    # Базовые состояния libvirt (libvirt.VIR_DOMAIN_*)
    libvirt_states = {
        -1: "DELETED",  # DELETED STATE
        0: "NOSTATE",  # VIR_DOMAIN_NOSTATE
        1: "RUNNING",  # VIR_DOMAIN_RUNNING
        2: "BLOCKED",  # VIR_DOMAIN_BLOCKED
        3: "PAUSED",  # VIR_DOMAIN_PAUSED
        4: "SHUTDOWN",  # VIR_DOMAIN_SHUTDOWN
        5: "SHUTOFF",  # VIR_DOMAIN_SHUTOFF
        6: "CRASHED",  # VIR_DOMAIN_CRASHED
        7: "PMSUSPENDED",  # VIR_DOMAIN_PMSUSPENDED
    }

    # Объединяем с кастомными состояниями если есть
    all_states = {**libvirt_states}

    # Конвертируем
    return all_states.get(state_int, f"UNKNOWN_{state_int}")
