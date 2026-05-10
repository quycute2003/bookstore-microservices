import os
import subprocess

# ĐIỀN USERNAME DOCKER HUB CỦA BẠN VÀO ĐÂY
DOCKER_USERNAME = "dunguyenquy"

services = [
    {"folder": "api-gateway", "image": f"{DOCKER_USERNAME}/api-gateway:latest"},
    {"folder": "auth-service", "image": f"{DOCKER_USERNAME}/auth-service:latest"},
    {"folder": "cart-service", "image": f"{DOCKER_USERNAME}/cart-service:latest"},
    {"folder": "catalog-service", "image": f"{DOCKER_USERNAME}/catalog-service:latest"},
    {"folder": "comment-rate-service", "image": f"{DOCKER_USERNAME}/comment-rate-service:latest"},
    {"folder": "order-service", "image": f"{DOCKER_USERNAME}/order-service:latest"},
    {"folder": "pay-service", "image": f"{DOCKER_USERNAME}/pay-service:latest"},
    {"folder": "product-service", "image": f"{DOCKER_USERNAME}/product-service:latest"},
    {"folder": "ship-service", "image": f"{DOCKER_USERNAME}/ship-service:latest"},
    {"folder": "recommender-ai-service", "image": f"{DOCKER_USERNAME}/recommender-ai-service:latest"},
    {"folder": "ai-behavior-service", "image": f"{DOCKER_USERNAME}/ai-behavior-service:latest"},
    {"folder": "nginx", "image": f"{DOCKER_USERNAME}/nginx-gateway:latest"},
]

print("=== BẮT ĐẦU BUILD VÀ PUSH IMAGE LÊN DOCKER HUB ===")
print(f"Username đang dùng: {DOCKER_USERNAME}")
print("Nếu username này sai, hãy mở file build_and_push.py ra để sửa lại dòng số 5 nhé!\n")

for svc in services:
    folder = svc["folder"]
    image = svc["image"]
    
    print(f"\n---> Đang xử lý: {folder}")
    
    # Bỏ qua nếu thư mục không tồn tại
    if not os.path.exists(folder):
        print(f"[CẢNH BÁO] Không tìm thấy thư mục {folder}, bỏ qua!")
        continue
        
    print(f"1. Building image: {image} ...")
    build_cmd = f"docker build -t {image} ./{folder}"
    subprocess.run(build_cmd, shell=True)
    
    print(f"2. Pushing image: {image} ...")
    push_cmd = f"docker push {image}"
    subprocess.run(push_cmd, shell=True)

print("\n=== HOÀN TẤT ĐẨY CODE LÊN DOCKER HUB! ===")
print("Giờ bạn có thể mở Google Cloud Shell và chạy lệnh: kubectl apply -f k8s/")
