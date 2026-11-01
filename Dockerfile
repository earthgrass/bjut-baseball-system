FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# 复制依赖文件
COPY requirements.txt .

# 升级 pip 并安装 Python 依赖 (默认使用官方源，速度最快且不会超时)
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p instance

# 将已校验的数据快照作为容器初始数据库
COPY deploy/seed/baseball_players.db /app/instance/baseball_players.db

# 构建时校验复制后的初始数据库，校验失败即终止构建
RUN python -c "from pathlib import Path; import hashlib; p=Path('/app/instance/baseball_players.db'); actual=hashlib.sha256(p.read_bytes()).hexdigest(); print('SEED_DB_SHA256=' + actual); assert actual == 'a76f7cc46686d690121e056bfd11a4ddc0133c134afd19ff5e40bd421ff82aec', 'Seed database checksum mismatch'"

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["python", "app.py"]
