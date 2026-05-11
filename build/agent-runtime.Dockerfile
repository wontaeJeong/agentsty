FROM busybox:1.36
COPY build/cask-stub-tui /usr/local/bin/cask-stub-tui
RUN chmod +x /usr/local/bin/cask-stub-tui
CMD ["/bin/sh", "-lc", "trap : TERM INT; while true; do sleep 3600; done"]
