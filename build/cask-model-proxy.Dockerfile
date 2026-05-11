FROM gcr.io/distroless/static-debian12:nonroot
COPY bin/linux/cask-model-proxy /cask-model-proxy
ENTRYPOINT ["/cask-model-proxy"]
