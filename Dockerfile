FROM alpine:3.23.3@sha256:25109184c71bdad752c8312a8623239686a9a2071e8825f20acb8f2198c3f659

COPY --chown=root:root ./src/ /app/
COPY --chown=root:root ./docker/entrypoint.sh /
WORKDIR /app

RUN apk add --update --no-cache samba-common-tools~=4 \
                                samba-common~=4 \
                                python3~=3.12 \
                                poetry~=2 \
                                curl~=8\
 && chown root:root /app \
 && mkdir /app/home \
 && adduser -S -D -H -h /app/home appuser \
 && chown appuser:root /app/home \
 && chmod 0700 /app/home \
 && chmod 0555 /app/app.py /entrypoint.sh \
 && mkdir /.cache && chown nobody:nobody /.cache

USER appuser
RUN poetry install

EXPOSE 8080
HEALTHCHECK --interval=1m --timeout=30s --start-period=5s --retries=3 CMD curl -H 'Host: '"$HOST" http://127.0.0.1:8080/"$WEBPATH" -f

ENTRYPOINT [ "/entrypoint.sh" ]
