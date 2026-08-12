# Imagem local do CRM offline -- construida e rodada dentro da rede
# interna. A imagem em si (python:3.11-slim) deve ser baixada uma unica
# vez de um mirror interno ou registry local; depois de construida, rodar
# o container nao requer nenhuma rede externa.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CRM_HOST=0.0.0.0
ENV CRM_PORT=8000

EXPOSE 8000

CMD ["python", "run.py"]
