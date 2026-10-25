ARG OPENCODE_VERSION=1.14.48
FROM ghcr.io/anomalyco/opencode:${OPENCODE_VERSION}

ENV HOME=/home/cask \
    XDG_CACHE_HOME=/home/cask/.cache \
    XDG_CONFIG_HOME=/home/cask/.config \
    XDG_DATA_HOME=/home/cask/.local/share \
    OPENCODE_DISABLE_AUTOUPDATE=true

RUN apk add --no-cache \
        bash \
        ca-certificates \
        curl \
        git \
        openssh-client \
        procps \
        tmux \
    && opencode --version

RUN addgroup -g 65532 cask \
    && adduser -D -u 65532 -G cask -h /home/cask -s /bin/bash cask \
    && mkdir -p /home/cask/.cache /home/cask/.config /home/cask/.local/share \
    && chown -R 65532:65532 /home/cask

COPY build/cask-stub-tui /usr/local/bin/cask-stub-tui
RUN chmod +x /usr/local/bin/cask-stub-tui

USER 65532:65532
ENTRYPOINT []
CMD ["/bin/bash", "-lc", "trap : TERM INT; while true; do sleep 3600; done"]
