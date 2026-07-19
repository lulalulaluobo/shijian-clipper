FROM alpine:3.22

ARG POCKETBASE_VERSION=0.38.2
ARG TARGETARCH
RUN apk add --no-cache curl unzip \
    && case "$TARGETARCH" in amd64) arch=amd64 ;; arm64) arch=arm64 ;; *) exit 1 ;; esac \
    && curl -fsSL "https://github.com/pocketbase/pocketbase/releases/download/v${POCKETBASE_VERSION}/pocketbase_${POCKETBASE_VERSION}_linux_${arch}.zip" -o /tmp/pocketbase.zip \
    && unzip /tmp/pocketbase.zip -d /pb \
    && rm /tmp/pocketbase.zip
COPY deploy/pocketbase/pb_migrations /pb/pb_migrations
WORKDIR /pb
ENTRYPOINT ["/pb/pocketbase"]
CMD ["serve", "--http=0.0.0.0:8090"]
