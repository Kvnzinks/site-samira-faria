# Samira Faria - Railway. Este Dockerfile exige os arquivos da interface.
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    DATA_DIR=/data \
    COOKIE_SECURE=1
COPY app.py /app/app.py
COPY static/ /app/static/
RUN python -c "from pathlib import Path; files=['/app/app.py','/app/static/index.html','/app/static/app.js','/app/static/style.css']; missing=[p for p in files if not Path(p).is_file()]; assert not missing, f'Arquivos ausentes: {missing}'; print('OK: arquivos da interface e do servidor encontrados')"
EXPOSE 8080
CMD ["python", "app.py"]
