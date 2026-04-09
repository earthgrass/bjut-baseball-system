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

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["python", "app.py"]