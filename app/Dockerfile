FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY peer.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. peer.proto

COPY peer.py controller.py gen_topology.py plot_exp10.py plot_exp11.py ./

ENV PYTHONUNBUFFERED=1
EXPOSE 50051

CMD ["python", "peer.py"]