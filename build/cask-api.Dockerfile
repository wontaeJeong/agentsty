FROM scratch
COPY bin/linux/cask-api /cask-api
USER 65532:65532
ENTRYPOINT ["/cask-api"]
