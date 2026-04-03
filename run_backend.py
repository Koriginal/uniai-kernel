import os
import sys
from pathlib import Path

# 将 backend 目录加入 python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

if __name__ == "__main__":
    import uvicorn
    # 本地开发建议从根目录直接运行此脚本
    print(f"🚀 UniAI Kernel Backend Starting from: {backend_dir}")
    # 切换到 backend 目录以确保相对路径（如 .env 加载）正常
    os.chdir(backend_dir)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
