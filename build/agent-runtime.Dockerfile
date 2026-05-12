FROM node:22-bookworm-slim

ARG OPENCODE_VERSION=1.14.48

ENV HOME=/home/cask \
    XDG_CACHE_HOME=/home/cask/.cache \
    XDG_CONFIG_HOME=/home/cask/.config \
    XDG_DATA_HOME=/home/cask/.local/share \
    OPENCODE_DISABLE_AUTOUPDATE=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        openssh-client \
        procps \
        tmux \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g "opencode-ai@${OPENCODE_VERSION}" \
    && opencode --version

RUN mkdir -p /home/cask/.cache /home/cask/.config /home/cask/.local/share \
    && chown -R 65532:65532 /home/cask

COPY build/cask-stub-tui /usr/local/bin/cask-stub-tui
RUN chmod +x /usr/local/bin/cask-stub-tui

CMD ["/bin/bash", "-lc", "trap : TERM INT; while true; do sleep 3600; done"]
