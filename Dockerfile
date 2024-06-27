FROM alpine:3.20.1@sha256:b89d9c93e9ed3597455c90a0b88a8bbb5cb7188438f70953fede212a0c4394e0

COPY --chown=root:root ./src/ /app/
COPY --chown=root:root ./docker/entrypoint.sh /
WORKDIR /app

RUN apk add --update --no-cache samba-common-tools~4.19 \
                                python3~3.12 \
                                curl~8 \
                                poetry~1.8 \
                                samba-common~4.19 \
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
