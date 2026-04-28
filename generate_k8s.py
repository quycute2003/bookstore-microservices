"""
Sinh toàn bộ K8s manifests cho hệ thống bookstore-microservice.
Chạy: python generate_k8s.py
Output: thư mục k8s/
"""
import os

# ── Cấu hình resource theo từng loại service ──────────────────
# Phân loại rõ để tránh OOMKilled và Pending
RESOURCES = {
    # req = lượng K8s *giữ chỗ* khi schedule → càng thấp càng dễ lên node
    # lim = trần thực tế container được dùng → giữ đủ để không crash
    "ai":       {"req_mem": "512Mi", "lim_mem": "2Gi",   "req_cpu": "50m",  "lim_cpu": "1000m"},
    "db":       {"req_mem": "256Mi", "lim_mem": "512Mi", "req_cpu": "50m",  "lim_cpu": "500m"},
    "neo4j":    {"req_mem": "256Mi", "lim_mem": "1Gi",   "req_cpu": "50m",  "lim_cpu": "500m"},
    "broker":   {"req_mem": "128Mi", "lim_mem": "512Mi", "req_cpu": "50m",  "lim_cpu": "300m"},
    "django":   {"req_mem": "64Mi",  "lim_mem": "256Mi", "req_cpu": "30m",  "lim_cpu": "300m"},
    "worker":   {"req_mem": "64Mi",  "lim_mem": "256Mi", "req_cpu": "30m",  "lim_cpu": "200m"},
    "nginx":    {"req_mem": "32Mi",  "lim_mem": "128Mi", "req_cpu": "20m",  "lim_cpu": "100m"},
}

# ── Danh sách services ─────────────────────────────────────────
services = [
    # ── Infrastructure ──
    {
        "name": "postgres-db",
        "port": 5432,
        "image": "postgres:15-alpine",
        "resource_type": "db",
        "pvc": {"mount": "/var/lib/postgresql", "size": "5Gi"},
        "init_script_configmap": "postgres-init-scripts",
        "env": {
            "POSTGRES_USER": "admin",
            "POSTGRES_PASSWORD": "123",
            "POSTGRES_DB": "default_db",
            "PGDATA": "/var/lib/postgresql/data/pgdata",
        },
    },
    {
        "name": "redis",
        "port": 6379,
        "image": "redis:7-alpine",
        "resource_type": "broker",
        "env": {},
    },
    {
        "name": "rabbitmq",
        "port": 5672,
        "image": "rabbitmq:3-management",
        "resource_type": "broker",
        "env": {
            "RABBITMQ_DEFAULT_USER": "guest",
            "RABBITMQ_DEFAULT_PASS": "guest",
        },
    },
    {
        "name": "neo4j",
        "port": 7687,
        "image": "neo4j:5-community",
        "resource_type": "neo4j",
        "pvc": {"mount": "/data", "size": "5Gi"},
        # enableServiceLinks: false để K8s không inject NEO4J_PORT_* vào pod
        # (neo4j đọc nhầm các biến đó thành config setting → crash)
        "disable_service_links": True,
        "env": {
            "NEO4J_AUTH": "neo4j/lumiere123",
            "NEO4J_server_memory_heap_initial__size": "256m",
            "NEO4J_server_memory_heap_max__size": "512m",
        },
    },

    # ── Application services ──
    {
        "name": "auth-service",
        "port": 8000,
        "image": "dunguyenquy/auth-service:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db"],
        "env": {},
    },
    {
        "name": "user-service",
        "port": 8000,
        "image": "dunguyenquy/user-service:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db"],
        "env": {
            "POSTGRES_DB": "user_db",
            "POSTGRES_USER": "admin",
            "POSTGRES_PASSWORD": "123",
            "POSTGRES_HOST": "postgres-db",
            "POSTGRES_PORT": "5432",
        },
    },
    {
        "name": "product-service",
        "port": 8000,
        "image": "dunguyenquy/product-service:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db"],
        "env": {
            "POSTGRES_DB": "product_db",
            "POSTGRES_USER": "admin",
            "POSTGRES_PASSWORD": "123",
            "POSTGRES_HOST": "postgres-db",
            "POSTGRES_PORT": "5432",
        },
    },
    {
        "name": "cart-service",
        "port": 8000,
        "image": "dunguyenquy/cart-service:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db"],
        "env": {},
    },
    {
        "name": "catalog-service",
        "port": 8000,
        "image": "dunguyenquy/catalog-service:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db"],
        "env": {},
    },
    {
        "name": "order-service",
        "port": 8000,
        "image": "dunguyenquy/order-service:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db", "rabbitmq"],
        "env": {},
    },
    {
        "name": "pay-service",
        "port": 8000,
        "image": "dunguyenquy/pay-service:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db", "rabbitmq"],
        "env": {},
    },
    {
        "name": "ship-service",
        "port": 8000,
        "image": "dunguyenquy/ship-service:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db", "rabbitmq"],
        "env": {},
    },
    {
        "name": "comment-rate-service",
        "port": 8000,
        "image": "dunguyenquy/comment-rate-service:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db"],
        "env": {},
    },
    {
        "name": "recommender-ai-service",
        "port": 8000,
        "image": "dunguyenquy/recommender-ai-service:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db"],
        "env": {},
    },
    {
        "name": "ai-behavior-service",
        "port": 8020,
        "image": "dunguyenquy/ai-behavior-service:latest",
        "resource_type": "ai",          # ← 2Gi limit, tránh OOMKilled
        "wait_for": ["postgres-db", "neo4j", "redis"],
        "env": {
            "REDIS_HOST": "redis",
            "REDIS_PORT": "6379",
            "POSTGRES_HOST": "postgres-db",
            "NEO4J_URI": "bolt://neo4j:7687",
            "NEO4J_USER": "neo4j",
            "NEO4J_PASSWORD": "lumiere123",
            "POSTGRES_USER": "admin",
            "POSTGRES_PASSWORD": "123",
            "POSTGRES_DB": "default_db",
        },
    },
    {
        "name": "api-gateway",
        "port": 8000,
        "image": "dunguyenquy/api-gateway:latest",
        "resource_type": "django",
        "wait_for": ["postgres-db"],
        "env": {},
    },
    {
        "name": "nginx",
        "port": 80,
        "image": "dunguyenquy/nginx-gateway:latest",
        "resource_type": "nginx",
        "wait_for": ["api-gateway"],
        "env": {},
    },

    # ── Workers (bất đồng bộ RabbitMQ) ──
    {
        "name": "order-worker",
        "port": None,
        "image": "dunguyenquy/order-service:latest",
        "resource_type": "worker",
        "command": ["python", "manage.py", "run_consumer"],
        "wait_for": ["postgres-db", "rabbitmq"],
        "env": {},
    },
    {
        "name": "pay-worker",
        "port": None,
        "image": "dunguyenquy/pay-service:latest",
        "resource_type": "worker",
        "command": ["python", "manage.py", "run_consumer"],
        "wait_for": ["postgres-db", "rabbitmq"],
        "env": {},
    },
    {
        "name": "ship-worker",
        "port": None,
        "image": "dunguyenquy/ship-service:latest",
        "resource_type": "worker",
        "command": ["python", "manage.py", "run_consumer"],
        "wait_for": ["postgres-db", "rabbitmq"],
        "env": {},
    },
]


# ── Builder functions ──────────────────────────────────────────

def build_init_containers(wait_for: list[str]) -> str:
    """
    Sinh initContainers chờ dependency sẵn sàng trước khi main container khởi động.
    Dùng nc (netcat) kiểm tra TCP connection.
    """
    if not wait_for:
        return ""

    port_map = {
        "postgres-db": 5432,
        "rabbitmq":    5672,
        "redis":       6379,
        "neo4j":       7687,
        "api-gateway": 8000,
    }

    lines = ["      initContainers:\n"]
    for dep in wait_for:
        port = port_map.get(dep, 8000)
        lines.append(f"""\
      - name: wait-for-{dep}
        image: busybox:1.35
        command: ['sh', '-c', 'until nc -z {dep} {port}; do echo waiting for {dep}; sleep 2; done']
""")
    return "".join(lines)


def build_pvc(name: str, size: str) -> str:
    return f"""\
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {name}-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: {size}
"""


def build_env_section(env: dict) -> str:
    if not env:
        return ""
    lines = ["        env:\n"]
    for k, v in env.items():
        lines.append(f"        - name: {k}\n")
        lines.append(f"          value: \"{v}\"\n")
    return "".join(lines)


def build_port_section(port) -> str:
    if port is None:
        return ""
    return f"        ports:\n        - containerPort: {port}\n"


def build_command_section(command: list) -> str:
    if not command:
        return ""
    cmd_str = ", ".join(f'"{c}"' for c in command)
    return f"        command: [{cmd_str}]\n"


def build_volume_mount(mount_path: str) -> str:
    return f"""\
        volumeMounts:
        - name: data
          mountPath: {mount_path}
"""


def build_volume_claim(pvc_name: str) -> str:
    return f"""\
      volumes:
      - name: data
        persistentVolumeClaim:
          claimName: {pvc_name}
"""


def build_readiness_probe(port) -> str:
    """HTTP probe cho web services, TCP probe cho DB/broker."""
    if port in (5432, 5672, 6379, 7687):
        return f"""\
        readinessProbe:
          tcpSocket:
            port: {port}
          initialDelaySeconds: 10
          periodSeconds: 5
"""
    if port == 80:
        return f"""\
        readinessProbe:
          httpGet:
            path: /
            port: {port}
          initialDelaySeconds: 5
          periodSeconds: 5
"""
    return f"""\
        readinessProbe:
          tcpSocket:
            port: {port}
          initialDelaySeconds: 15
          periodSeconds: 10
          failureThreshold: 6
"""


def build_deployment(svc: dict) -> str:
    name         = svc["name"]
    image        = svc["image"]
    res_type     = svc.get("resource_type", "django")
    res          = RESOURCES[res_type]
    port         = svc.get("port")
    env          = svc.get("env", {})
    command      = svc.get("command", [])
    wait_for     = svc.get("wait_for", [])
    pvc_info     = svc.get("pvc")

    init_section    = build_init_containers(wait_for)
    env_section     = build_env_section(env)
    port_section    = build_port_section(port)
    cmd_section     = build_command_section(command)
    readiness       = build_readiness_probe(port) if port else ""
    svc_links       = "      enableServiceLinks: false\n" if svc.get("disable_service_links") else ""

    # Volume mounts: PVC data + optional init-script ConfigMap
    configmap_name  = svc.get("init_script_configmap")
    if pvc_info and configmap_name:
        vol_mount = (
            f"        volumeMounts:\n"
            f"        - name: data\n"
            f"          mountPath: {pvc_info['mount']}\n"
            f"        - name: init-scripts\n"
            f"          mountPath: /docker-entrypoint-initdb.d\n"
        )
        vol_claim = (
            f"      volumes:\n"
            f"      - name: data\n"
            f"        persistentVolumeClaim:\n"
            f"          claimName: {name}-pvc\n"
            f"      - name: init-scripts\n"
            f"        configMap:\n"
            f"          name: {configmap_name}\n"
            f"          defaultMode: 0755\n"
        )
    elif pvc_info:
        vol_mount = build_volume_mount(pvc_info["mount"])
        vol_claim = build_volume_claim(f"{name}-pvc")
    else:
        vol_mount = ""
        vol_claim = ""

    return f"""\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
{svc_links}\
{init_section}\
      containers:
      - name: {name}
        image: {image}
        imagePullPolicy: Always
{cmd_section}\
{port_section}\
{env_section}\
{readiness}\
{vol_mount}\
        resources:
          requests:
            memory: "{res['req_mem']}"
            cpu: "{res['req_cpu']}"
          limits:
            memory: "{res['lim_mem']}"
            cpu: "{res['lim_cpu']}"
{vol_claim}\
"""


def build_service(svc: dict) -> str:
    name = svc["name"]
    port = svc["port"]
    # Chỉ nginx expose ra ngoài bằng LoadBalancer
    svc_type = "LoadBalancer" if name == "nginx" else "ClusterIP"

    return f"""\
apiVersion: v1
kind: Service
metadata:
  name: {name}
  labels:
    app: {name}
spec:
  type: {svc_type}
  selector:
    app: {name}
  ports:
    - port: {port}
      targetPort: {port}
      protocol: TCP
"""


# ── Postgres init SQL ConfigMap ────────────────────────────────
INIT_SQL = """\
CREATE DATABASE IF NOT EXISTS user_db;
CREATE DATABASE IF NOT EXISTS staff_db;
CREATE DATABASE IF NOT EXISTS manager_db;
CREATE DATABASE IF NOT EXISTS customer_db;
CREATE DATABASE IF NOT EXISTS catalog_db;
CREATE DATABASE IF NOT EXISTS book_db;
CREATE DATABASE IF NOT EXISTS cart_db;
CREATE DATABASE IF NOT EXISTS order_db;
CREATE DATABASE IF NOT EXISTS ship_db;
CREATE DATABASE IF NOT EXISTS pay_db;
CREATE DATABASE IF NOT EXISTS comment_rate_db;
CREATE DATABASE IF NOT EXISTS recommender_ai_db;
CREATE DATABASE IF NOT EXISTS gateway_db;
CREATE DATABASE IF NOT EXISTS auth_db;
CREATE DATABASE IF NOT EXISTS clothes_db;
CREATE DATABASE IF NOT EXISTS ai_behavior_db;
CREATE DATABASE IF NOT EXISTS product_db;
"""

def build_postgres_init_configmap() -> str:
    db_names = [
        "user_db", "staff_db", "manager_db", "customer_db",
        "catalog_db", "book_db", "cart_db", "order_db",
        "ship_db", "pay_db", "comment_rate_db", "recommender_ai_db",
        "gateway_db", "auth_db", "clothes_db", "ai_behavior_db", "product_db",
    ]
    # createdb bỏ qua nếu DB đã tồn tại (|| true)
    cmds = "\n".join(
        f"    createdb -U $POSTGRES_USER {db} 2>/dev/null || true"
        for db in db_names
    )
    return f"""\
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-init-scripts
data:
  init-databases.sh: |
    #!/bin/bash
    set -e
{cmds}
"""


# ── Main ───────────────────────────────────────────────────────
os.makedirs("k8s", exist_ok=True)

# Sinh ConfigMap init SQL cho postgres
with open("k8s/postgres-init-configmap.yaml", "w") as f:
    f.write(build_postgres_init_configmap())

for svc in services:
    name = svc["name"]

    # Deployment
    with open(f"k8s/{name}-deployment.yaml", "w") as f:
        f.write(build_deployment(svc))

    # Service (chỉ khi có port)
    if svc.get("port") is not None:
        with open(f"k8s/{name}-service.yaml", "w") as f:
            f.write(build_service(svc))

    # PersistentVolumeClaim (chỉ stateful services)
    if svc.get("pvc"):
        with open(f"k8s/{name}-pvc.yaml", "w") as f:
            f.write(build_pvc(name, svc["pvc"]["size"]))

print(f"✅ Generated {len(services)} deployments")
print("   PVCs:     postgres-db (5Gi), neo4j (5Gi)")
print("   Fixes:    OOMKilled (ai: 2Gi), initContainers, readiness probes")
print("\nDeploy:")
print("  kubectl apply -f k8s/")
