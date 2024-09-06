FROM python:latest
ENV PKG="elva-0.0.1-py3-none-any.whl"
RUN --mount=type=bind,source=dist/$PKG,target=/tmp/$PKG \
    pip install /tmp/$PKG
ENTRYPOINT ["elva"]
CMD ["-m", "yjs", "serve", "0.0.0.0", "8000"]
