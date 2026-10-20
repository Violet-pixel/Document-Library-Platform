# Processador de documentos: Java 21 + PDFBox. Lê PDF e DOCX do volume /data e devolve JSON.

FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -q package -DskipTests

FROM eclipse-temurin:21-jre-noble
RUN apt-get update \
 && apt-get install -y --no-install-recommends fontconfig fonts-dejavu-core curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --home-dir /app app \
 && mkdir -p /data \
 && chown app:app /data

WORKDIR /app
COPY --from=build /build/target/processor.jar /app/processor.jar
# O PDFBox guarda o cache de fontes na pasta do usuário (/app).
RUN chown app:app /app

ENV PROCESSOR_PORT=8090 \
    PROCESSOR_DATA_ROOT=/data \
    PROCESSOR_CONCURRENCY=2

# UID/GID 10001 é o mesmo usuário da imagem web: os dois escrevem no volume /data.
USER app
EXPOSE 8090
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=6 \
  CMD curl -fsS http://localhost:8090/health || exit 1
ENTRYPOINT ["java","-XX:MaxRAMPercentage=75","-Djava.awt.headless=true","-jar","/app/processor.jar"]
