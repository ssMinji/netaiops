FROM public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

RUN pip install aws-opentelemetry-distro>=0.10.1

ENV AWS_REGION=us-east-1
ENV AWS_DEFAULT_REGION=us-east-1

ENV DOCKER_CONTAINER=1

RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 8080
EXPOSE 8000

COPY . .

CMD ["opentelemetry-instrument", "python", "-m", "main"]
