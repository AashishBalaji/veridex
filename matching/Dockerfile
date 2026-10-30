# Runs the matching pipeline as a one-shot batch job (data generation
# + Spark blocking/FAISS/classifier run), writing artifacts/ to a
# volume the backend's init container then reads from. Not a
# long-running service -- there's no server here, just `python
# generate_data.py && python pipeline.py`.
FROM eclipse-temurin:21-jre-jammy AS java-base
# PySpark needs a JVM on PATH even though the driver logic is Python.

FROM python:3.11-slim
COPY --from=java-base /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="$JAVA_HOME/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY generate_data.py pipeline.py explain.py ./

CMD ["sh", "-c", "python generate_data.py && python pipeline.py"]
