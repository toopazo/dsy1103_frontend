#!/bin/bash
set -e

echo "=============================="
echo " DSY1103 Spring Runner"
echo " Port: ${PORT:-8080}"
echo "=============================="

# Inject secrets file if provided (mounted at /secrets/app-secrets.properties).
# Copies into the source tree BEFORE mvn/gradle build so Spring finds it on the classpath.
SECRETS_TARGET="src/main/resources/application-secrets.properties"
if [ -f "/secrets/app-secrets.properties" ]; then
    echo "[runner] Injecting secrets file..."
    mkdir -p src/main/resources
    cp /secrets/app-secrets.properties "$SECRETS_TARGET"
elif [ ! -f "$SECRETS_TARGET" ]; then
    # Create empty placeholder so Spring Boot doesn't warn on missing profile file
    mkdir -p src/main/resources
    echo "# auto-generated placeholder" > "$SECRETS_TARGET"
fi

# Build: Maven or Gradle
if [ -f "mvnw" ]; then
    echo "[runner] Building with Maven Wrapper..."
    chmod +x mvnw
    ./mvnw package -DskipTests
    JAR=$(ls target/*.jar 2>/dev/null | grep -v '\.original$' | head -1)

elif [ -f "gradlew" ]; then
    echo "[runner] Building with Gradle Wrapper..."
    chmod +x gradlew
    ./gradlew bootJar
    JAR=$(ls build/libs/*.jar 2>/dev/null | grep -v '\-plain\.jar$' | head -1)

else
    echo "[runner] ERROR: no mvnw or gradlew found in /app"
    exit 1
fi

if [ -z "$JAR" ]; then
    echo "[runner] ERROR: no JAR produced after build"
    exit 1
fi

echo "[runner] Starting: $JAR on port ${PORT:-8080}"
exec java -jar "$JAR" --server.port="${PORT:-8080}"
