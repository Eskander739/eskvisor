class ApiVersion:
    V0 = "/api/v0"
    V1 = "/api/v1"
    V2 = "/api/v2"


KEY_DIR = "/eskvisor/.ssh/"
KEY_NAME = "eskvisor_master_ed25519"
DEFAULT_AGENT_DIR = "/home/eska/eskvisor_agent.tar.gz"
TMP_AGENT_DIR = "/tmp/eskvisor_agent_package.tar.gz"
SCRIPT_INSTALL_DIR = "/opt/eskvisor/agent/install_agent.sh"
PROD_ENV = "/etc/eskvisor/backend.env"

# DB_POOL_SIZE = 15  # для прода
# REDIS_POOL_SIZE = 10  # для прода
# WS_POOL_SIZE = 15  # для прода

DB_POOL_SIZE = 2  # для тестов
REDIS_POOL_SIZE = 2  # для тестов
WS_POOL_SIZE = 2  # для тестов
