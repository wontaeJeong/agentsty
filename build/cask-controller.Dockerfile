FROM scratch
COPY bin/linux/cask-controller /cask-controller
USER 65532:65532
ENTRYPOINT ["/cask-controller"]
