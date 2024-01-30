FROM python:latest
COPY websocket-server.py ./
RUN pip install websockets anyio click
ENTRYPOINT python websocket-server.py "0.0.0.0" 8000
