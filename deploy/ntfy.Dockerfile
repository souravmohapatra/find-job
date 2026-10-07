ARG NTFY_IMAGE=binwiederhier/ntfy@sha256:f2419f405127afa868f10985c1a41449e673477cee1eb19994339a5ae8b592e7
FROM ${NTFY_IMAGE}
USER root
RUN mkdir -p /var/lib/ntfy && chown 10001:10001 /var/lib/ntfy
USER 10001:10001
