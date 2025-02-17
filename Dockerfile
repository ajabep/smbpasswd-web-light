FROM alpine:3.21.3@sha256:a8560b36e8b8210634f77d9f7f9efd7ffa463e380b75e2e74aff4511df3ef88c

COPY --chown=root:root ./src/ /app/
COPY --chown=root:root ./docker/entrypoint.sh /
WORKDIR /app

RUN apk add --update --no-cache samba-common-tools=4.20.6-r1 \
                                python3=3.12.8-r1 \
                                curl=8.11.1-r0 \
                                poetry=1.8.4-r0 \
                                samba-common=4.20.6-r1 \
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
